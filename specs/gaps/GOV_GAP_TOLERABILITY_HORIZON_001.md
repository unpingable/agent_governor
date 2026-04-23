# GOV_GAP_TOLERABILITY_HORIZON_001

## Title
Tolerability Horizon: representing "real adverse, currently tolerable" on gate receipts

## Status
Gap spec — 3.x (new receipt axis, not a 2.x feature). Small scope,
load-bearing connective tissue for Night Shift dogfood.

## Origin

2026-04-23 constellation-wide confirmation of the
**compress-don't-widen** invariant as the third independent
instance inside the observatory family:

1. driftwatch **vintage control** narrowed/dissolved a hosting-locus
   claim that had been aggregated across cohorts.
2. driftwatch **`state_kind`** axis prevents maintenance debt from
   being rendered as fresh incident.
3. driftwatch + nq **tolerability horizon** prevents "real adverse
   condition" from collapsing into "act now."

The first two are substrate-honesty inside the observatory family.
The third is where governor needs a matching concept, because
governor is the consumer of adverse findings that will be routed
through gate receipts into downstream action (Night Shift,
runtime supervisor, etc).

Cross-references:
- driftwatch lesson `mem_b9caac4084f343d5907b63c845a6e837` (2026-04-23)
- nq mirror `mem_d5df7a0fb6b74283b662a2717aa3c16f` (2026-04-23)
- observatory-family mode-phase lesson `mem_7cf6b28a711148f4a62ca5715f99b67a`
- `docs/information_architecture_registers.md` rule #4 ("refusal
  and partiality need homes")

## Problem Statement

Governor gate receipts currently carry a verdict vocabulary of
roughly `{block, warn, observe, allow, escalate, require_human}`.
That vocabulary answers **"what should happen right now?"** It does
not answer **"how long is it acceptable for this condition to
remain adverse?"**

The consequence is a collapse stack that the observatory family
named explicitly on 2026-04-23:

> badness → urgency → intervention → escalation

Each arrow is an inference the consumer is currently forced to
make, because the receipt does not carry a horizon axis. An LLM
consumer (Night Shift, or any other agent downstream of governor)
will by default collapse "adverse" into "urgent" into "act now."
That collapse is exactly the failure mode governor is designed to
prevent, but at a layer the current verdict vocabulary cannot see.

Concretely, governor cannot today represent:

- "This evidence is adverse, but tolerable indefinitely."
  *(e.g. an advisory signal that has crossed a threshold but the
  policy explicitly permits continued operation.)*
- "This violation is adverse, tolerable until a named window."
  *(e.g. a drift observation that should be reconciled at the
  next planned checkpoint, not immediately.)*
- "This finding is adverse, tolerable only for observation
  purposes — no intervention authorized."
- "This finding is adverse and not tolerable — act now."

All four end up rendered as the same `warn` or `block`, and the
horizon collapses into the consumer's imagination.

## Non-goals

- **Not a new verdict.** Horizon is orthogonal to verdict, not a
  replacement for it.
- **Not a severity grading.** Severity asks "how bad"; horizon
  asks "how long is this bad acceptable." Independent axes.
- **Not an override.** Overrides (`src/governor/overrides.py`) are
  authorized exceptions to an invariant. Horizon describes
  tolerability of the underlying adverse condition, which may or
  may not also be under an active override.
- **Not a scar.** Scars record past failures and gate future
  actions with hysteresis. Horizon describes the current
  condition's continued admissibility, not historical memory.
- **Not a TTL.** TTLs (`src/governor/ttl.py`) govern freshness
  decay of a claim's believability. Horizon governs the
  admissibility of acting (or not acting) on an adverse condition.
- **Not inferred.** Horizon must be declared by producer or bound
  by consumer policy. Never smart-defaulted from verdict or
  severity.

## Existing Governor Coverage

### Adjacent but distinct

| Concept | Module | What it does | Why it's not horizon |
|---|---|---|---|
| Override | `src/governor/overrides.py` | Time-bounded scoped exception for an invariant anchor | Grants *authority* to violate; horizon describes *condition tolerability* |
| TTL volatility | `src/governor/ttl.py` | Claim freshness decay | Governs belief, not action-gate admissibility |
| Scars | `src/governor/scars.py` | Post-failure action restriction | Historical; horizon is present-tense |
| Regime detection | `src/governor/regime.py` | ELASTIC/WARM/DUCTILE/UNSTABLE | System-wide stress; horizon is per-finding |
| Claim status | `src/governor/epistemic.py` | PROPOSED/SUPPORTED/CONTESTED/… | Claim lifecycle; horizon is action admissibility |
| Gate exceptions | `src/governor/evidence_gate.py` | Logged-exception-to-proceed | Post-hoc "we went ahead"; horizon is pre-hoc "we may defer" |

None of these carry the axis the observatory lesson names.

### Genuinely absent

A first-class **tolerability horizon** field on gate receipts, with
basis and expiry, that survives rendering through downstream
consumers (Night Shift, runtime supervisor, dashboard).

## Design

### A1 — Horizon enum

Closed vocabulary, frozen at v1:

- **`none`** — not adverse; this receipt does not carry tolerance
  semantics.
- **`now`** — adverse and not tolerable; act now.
- **`hours`** — adverse; tolerable for hours (requires expiry).
- **`business_hours`** — adverse; tolerable until the next
  scheduled business window (requires window anchor).
- **`scheduled`** — adverse; tolerable until a named scheduled
  event (requires event id).
- **`observe_only`** — adverse; no intervention authorized;
  tolerable for as long as the condition persists (no expiry).
- **`indefinite`** — adverse; tolerable indefinitely under current
  policy (requires declaring policy id).

Missing field ≠ `none`. Missing field means "producer did not
declare." Policy at the consumer decides whether undeclared
horizon is treated as `now` (fail-closed) or `observe_only`
(fail-open). Default policy should be **fail-closed**: undeclared
horizon on an adverse finding escalates to `now`.

### A2 — Basis field

Every non-`none` horizon carries:

- **`horizon_basis_id`** — policy or declaration that authorized
  the tolerance (points to a policy artifact, invariant override,
  or explicit operator assertion).
- **`horizon_expiry`** — ISO 8601 timestamp at which the declared
  tolerance expires and the condition re-escalates (required for
  `hours`, `business_hours`, `scheduled`; optional for
  `observe_only` and `indefinite`).
- **`horizon_basis_hash`** — content hash of the basis artifact,
  same discipline as standing receipt parent refs.

Horizon without basis is rejected at receipt construction, same
discipline as gate receipt required fields.

### A3 — Receipt integration

Tolerability fields live on the gate receipt timing fragment (new
nested block `horizon`) so receipts without horizon semantics
remain unchanged. Receipts carrying horizon must pass the standing
validator's schema check — unknown-fields discipline applies.

```
gate_receipt.horizon = {
    "class": "hours",
    "basis_id": "policy:advisory_retention.v0_1",
    "basis_hash": "sha256:...",
    "expiry": "2026-04-24T03:00:00Z"
}
```

### A4 — Consumer contract

Downstream consumers (Night Shift, runtime supervisor, dashboard)
read `horizon` *before* `verdict` when deciding action. The contract:

- `horizon == "now"` or missing-under-fail-closed → act on verdict
- `horizon in {hours, business_hours, scheduled}` → check expiry;
  if past expiry, escalate to `now`; otherwise defer to horizon
  policy
- `horizon == "observe_only"` → render to operator surfaces, do
  not emit intervention even if verdict would authorize one
- `horizon == "indefinite"` → render, do not surface as alert
  unless policy changes

This is the observatory-family consumer-side wrinkle discipline
applied to horizon: *recompute from raw inputs, do not consume the
verdict blindly*. The verdict is still authoritative for "what
governor decided"; the horizon is authoritative for "how urgent
the consumer may treat it."

### A5 — Consumer persistence obligation (stateful multi-run consumers)

**Added 2026-04-23 after Night Shift dogfood pass.** The read-side
contract above is sufficient for single-evaluation consumers. It
is **not** sufficient for consumers that span runs.

Concrete failure mode (Night Shift): run A at t0 defers on a
receipt carrying `horizon=hours`, `expiry=t0+4h`. Run B at t0+5h
re-evaluates the underlying condition. Without persisted
deferral state, run B sees the condition as a **fresh arrival**,
not as **expired tolerance** — which is the exact collapse stack
(`badness → urgency → intervention → escalation`) horizon was
introduced to prevent.

**Rule:**

> For any stateful consumer that spans runs and claims horizon
> fidelity, deferred horizons in `{hours, business_hours, scheduled}`
> create a persistence obligation at the moment of deferral, not
> just a read contract.

**What must be persisted at deferral:**

- The deferral event (this receipt was deferred, not acted on)
- `horizon_expiry` (so later runs can compute expired vs active)
- `horizon_basis_id` + `horizon_basis_hash` (so later runs can
  verify the basis still applies unchanged)
- The subject identifier the condition resolves against (so the
  next run's re-observation can be correlated)

**What the persistence enables a later run to distinguish:**

- **`expired_tolerance`** — horizon expiry has passed. Re-escalate
  to `now`. Not a fresh incident; a matured deferral.
- **`tolerated_active`** — expiry not yet reached and basis hash
  still matches the live basis artifact. Continue deferral.
- **`basis_invalidated`** — basis hash no longer matches (policy
  changed, override revoked). Re-escalate to `now` regardless of
  expiry.
- **`fresh_arrival`** — no prior deferral recorded for this
  subject. Evaluate from scratch.

**Scope of the obligation:**

Stateless consumers (single-run, no cross-run read path) are
**exempt**. They cannot carry lineage and their horizon semantics
are scoped to a single evaluation. This is not a universal
write-contract — it is a contract for consumers that *claim*
horizon fidelity across runs.

**Night Shift landing point (confirmed workable):**

`AttentionState::WatchUntil(T, basis=B)` already exists
(scheduler/crates/nightshiftd packet.rs:17–24) and is the natural
slot. The reconciler writes it on horizon-deferred verdicts;
subsequent runs read it to produce the four-way distinction above.
Pure-additive on the Night Shift side — no enum widening, no
verdict surgery.

**Non-collisions held explicit:**

- Freshness TTL (`src/governor/ttl.py`) and horizon expiry are
  **orthogonal**. Evidence staleness and tolerance window are
  different species. Do not fold. A receipt may have stale
  evidence *and* an unexpired horizon, or fresh evidence *and* an
  expired horizon. Both axes stand.
- Basis validation on re-read is not a re-run of the original
  basis evaluation — it is a hash check against the artifact as
  stored. If the operator changes the basis artifact, the hash
  diverges, and the receipt is treated as `basis_invalidated`.

### A6 — v1 enum collapse acknowledgement (Night Shift probe)

Night Shift probe 1 revealed that "adverse, do not intervene" and
"intervention meaningless" both collapse into the same
`observe_only` class in v1. Night Shift's current `ProposedActionKind::Advisory`
at authority `Observe` inherits this collapse (scheduler/crates/nightshiftd
packet.rs:76–80, agenda.rs:19–26). This is acceptable for v1.

**Note for later:** if live receipt distribution shows the two
postures driving different downstream consequences — e.g.
different staleness tolerances, different operator-surface
rendering — the split gets its own gap spec. Not deferred on
principle; deferred on absence of evidence it matters. Same
discipline as the compress-don't-widen invariant this gap exists
to enforce: don't split the class until the class is observably
too wide.

## Module Touchpoints

- `src/governor/gate_receipt.py` — add `horizon` optional block,
  schema validation, content-hash inclusion.
- `src/governor/evidence_gate.py` — producers of gate receipts
  gain a horizon parameter; default `None`.
- `src/governor/overrides.py` — cross-reference: active overrides
  may inject horizon automatically into receipts governed by the
  override's scope.
- `src/governor/viewmodel.py` — expose horizon in schema v2.
- `src/governor/daemon.py` — receipts RPC returns horizon; new
  query `receipts.horizon_expiring_soon(window)` useful for the
  dashboard and Night Shift reconciler.
- New module **not required** — horizon is a data shape plus
  consumer contract, not a subsystem.

## Invariants

1. **Horizon is declared, not inferred.** No governor module
   derives horizon from verdict or severity. If undeclared,
   policy-bound default applies at the consumer.
2. **Horizon requires basis.** Non-`none` horizon without
   `horizon_basis_id` and `horizon_basis_hash` is a schema
   violation, rejected at receipt construction.
3. **Horizon expiry is real wall-clock time.** Not decay, not
   dwell. When `now() >= horizon_expiry`, the receipt is treated
   as `horizon == "now"` until re-emitted.
4. **Horizon does not soften verdict.** A `block` verdict with
   `horizon == "hours"` still blocks; it merely declares that the
   underlying adverse condition may persist without forcing
   immediate remediation. Action-gating uses verdict; urgency
   routing uses horizon.
5. **Missing field ≠ zero.** Absent horizon means "producer did
   not declare," not "tolerable indefinitely." Same discipline as
   signal envelope `missing ≠ zero`.
6. **Horizon is content-bound to its basis.** If the basis
   artifact changes after the receipt is emitted, the receipt
   becomes stale; re-emission required.
7. **Deferral persistence is bounded to stateful consumers.**
   The A5 write obligation applies only to consumers that span
   runs and claim horizon fidelity. Stateless single-evaluation
   consumers are exempt. Governor does not universalize the
   contract; it scopes the obligation to consumers whose
   architecture actually requires lineage.
8. **Freshness TTL and horizon expiry are orthogonal.** Evidence
   staleness (`src/governor/ttl.py`) and tolerance window are
   different species. Never fold. A receipt may simultaneously
   carry stale evidence and an unexpired horizon, or fresh
   evidence and an expired horizon. Both axes stand.

## Open Questions

1. **Does horizon ever downgrade verdict?** Probably not — keeping
   the axes independent is the whole point — but edge cases
   (`observe_only` with `block` verdict) may need explicit
   rendering guidance.
2. **Where does the default policy live?** The fail-closed default
   for undeclared horizon on adverse findings is a policy
   declaration, not a hardcode. Lives in a ratified policy
   artifact (new), referenced by the gate receipt system.
3. ~~**Does Night Shift need horizon before governor implements
   it, or vice versa?**~~ **Resolved 2026-04-23 via Night Shift
   dogfood pass.** v1 horizon enum workable as-is. One delta
   named and integrated (A5 persistence obligation). Pure-
   additive on Night Shift side; `AttentionState::WatchUntil(T, basis=B)`
   is the landing point. Both land together behind a feature flag
   until the contract shape is confirmed by a second dogfood pass.
4. **Interaction with scars.** A scar may ingest a past receipt's
   horizon — does horizon at the moment of failure influence scar
   stiffness? Probably yes (a failure under `now` horizon is a
   harder scar than one under `hours`), but that's a Phase-B
   question.
5. **Multi-producer receipts.** When a receipt aggregates multiple
   sources with different declared horizons, aggregation rule is
   **min across sources** (conservative). Documented, not
   inferred.

## Acceptance criteria

- [ ] `GateReceipt.horizon` optional block accepted by schema
      validator, rejected when malformed.
- [ ] `evidence_gate.produce_receipt` accepts `horizon` kwarg;
      receipts without horizon continue to pass existing tests
      unchanged.
- [ ] Standing validator recognizes the nested block under
      unknown-fields discipline (either allowlisted or explicitly
      declared in envelope keys).
- [ ] At least one producer (advisory signal path) emits horizon
      in a test fixture demonstrating all seven enum values.
- [ ] Night Shift reconciler writes `AttentionState::WatchUntil`
      on horizon-deferred verdicts in `{hours, business_hours,
      scheduled}`; subsequent runs read it to produce the four-way
      distinction (expired_tolerance / tolerated_active /
      basis_invalidated / fresh_arrival).
- [ ] Cross-run fixture: run A defers at t0, run B at t0+5h
      correctly distinguishes expired_tolerance from fresh_arrival
      for the same subject.
- [ ] Daemon RPC returns horizon in `receipts.detail`.
- [ ] A policy declaration exists for the fail-closed undeclared-
      horizon default.
- [ ] Night Shift adapter (`GOV_GAP` for Night Shift contract,
      separate) consumes horizon in reconciler before verdict.

## Relationship to other gaps

- **Night Shift Governor adapter** (observatory-family next_action
  `mem_42cc0383e146473b8099b3bde66d4197`) — horizon is the piece
  that lets the adapter carry the observatory family's semantics
  without the LLM consumer collapsing them.
- **TEMPO_AWARE_GOVERNANCE** — horizon is wall-clock and policy-
  bound; tempo is ratio-based and plant-relative. They are
  orthogonal axes of "when." Horizon says "until when is this
  tolerable"; tempo says "relative to what rate does this matter."
- **CONTINUITY_BEARING_SYSTEMS** — horizon is the per-receipt
  temporal admissibility axis that complements the per-system
  continuity-bearing audit. Continuity asks "is the system still
  standing"; horizon asks "is this finding still admissible to
  leave alone."

## Compressed line

> Temporary admissibility must carry horizon, basis, and expiry; otherwise tolerated badness fossilizes into standing permission.

(Continuity phrasing of the same rule. The sharp version for
governor-side: **horizon is declared, basis is cited, expiry is
real, missing means fail-closed.**)
