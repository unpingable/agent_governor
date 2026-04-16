# STRUCTURED_EVIDENCE_AND_PROMOTION_GAP

## Status
Proposed (2026-04-16)

## Origin
Night Shift framing pass (`~/git/scheduler`, 2026-04-15 → 04-16) plus
NQ and nq-witness gap specs drafted in the same window. Night Shift is
the forcing function, but the missing pieces are broader than a single
adapter.

## Thesis

> Night Shift forces Governor to distinguish between authorizing an
> action and authorizing a transition in standing.

That is the conceptual jump. Everything else in this spec is mechanical.

Today, Governor authorizes *per-action*: scope check, gate verdict,
evidence hash. Night Shift's promotion ladder requires *lifecycle*
authorization — "may this run cross from propose to request" — which is
not the same thing. Adjacent to that, witness-backed evidence
(nq-witness) demands structured evidence types where coverage, standing,
and freshness are first-class fields — not opaque bytes under a hash.

Put bluntly: opaque `evidence_hash` stops being sufficient once
witnesses declare what they can testify about and what they cannot see.
Without a structured evidence type, Governor is hashing bytes and
calling it epistemology.

## What Already Exists (reusable, do not reinvent)

| NS/NQ need | Existing Governor surface | Wrapping required |
|------------|---------------------------|-------------------|
| `record_receipt(event)` | `gate_receipt` (receipt_v1, content-addressed) | New gate names (`nightshift.*`) + RPC method |
| `check_policy(request)` | Scope governor + gate receipts | Named-policy dereference layer |
| Transport (stdio / Unix socket) | Daemon JSON-RPC, Content-Length framing | None — already correct |
| Operator approval UX | Runtime supervisor intervention queue | Agenda-scoped analog |
| Tool-class authority (MCP_CALL) | Scope governor tool contracts | Add call-class axis |
| NETWORK_EGRESS capability | Egress gate | None — already done |
| Receipt canonicality | Receipt kernel hash chain | None — already canonical |

## Genuinely New Seams (no home today)

### 1. `policy_id` resolver
Named, addressable, resolvable policy handles. NS agendas declare
`policy_id`; Governor must resolve → validate → return a handle the
run can be pinned to. Today policies are embedded/positional, not
addressable. First obviously missing primitive. Without it, every
agenda is carrying around policy soup and Governor is validating
blobs.

### 2. `authorize_transition(run_id, from, to)`
Lifecycle authorization, distinct from per-action policy check.
Runtime supervisor has session state but does not express "allowed
to move from stage=X to stage=Y." "May call tool X" is not "may
promote this run from propose → request → apply." Governor needs
an explicit home for the second.

### 3. Verdict TTL / revalidation
Gate receipts are timestamped but not TTL'd. `require_fresh_approval`
has no home. A decision that was valid at 11:00 PM may not have
standing at 3:00 AM. Timestamp alone is not enough — need TTL,
freshness requirement, revalidation obligation. Time drift is the
whole Night Shift problem.

### 4. Witness evidence type + standing gate
First structured evidence type. nq-witness specifies `coverage`,
`standing`, `cannot_testify`, `freshness` declarations. Governor's
`evidence_hash` is opaque. Need a `WitnessEvidence` dataclass the
gate can check standing-vs-claim-subject against. Load-bearing
seam — without it, every receipt emitted for an NS/NQ run is hashing
bytes whose meaning lives elsewhere.

### 5. Finding ingest bridge
`nq findings export --changed-since GEN --format jsonl` → Governor
claim. No bridge today; epistemic ledger has `GroundedClaim` but no
NQ adapter. Traceable chain required:

```text
NQ finding/export → Governor claim/evidence ingest → standing check →
Night Shift packet / promotion attempt → Governor authorization receipt
```

Without it, the observatory and the authority plane are dating, not
married.

### 6. Capability namespace registry
Small, versioned registry for NS/NQ capability vocabulary:
`NIGHTSHIFT_PROMOTE`, `MCP_CALL` (by call-class), `PAGE_HUMAN`,
`PUBLISH_ARTIFACT`. Scope governor has axes but not domain
capabilities. Keep minimal — otherwise capability names become
folklore.

### 7. Degraded-mode contract
NS needs authority-plane state as a *named* enum, not inferred.
Governor must define the contract so NS degrades loudly (lower
ceiling, refuse `stage+` classes) rather than guessing. Degraded
mode is where all the lies happen.

Sketch:

```text
authority_plane:
  present    # Governor reachable, policy/approval/TTL surfaces all live
  degraded   # reachable but one or more surfaces unavailable
             # (approval queue down, policy resolver stale, etc.)
  absent     # no Governor at all
```

`degraded` is deliberately one state covering multiple shapes
(stale policy, unavailable approval, unresolvable `policy_id`).
Each shape names its *reason* in the receipt so "degraded" does
not quietly overload into "absent." Future sub-states may graduate
out of `degraded` when their handling diverges enough to justify
separate enum values.

## Claims This Gap Makes Explicit

1. **Opaque evidence hashes are insufficient** once witnesses declare
   standing. Governor needs at least one structured evidence type.
2. **Per-action authorization ≠ lifecycle transition authorization.**
   They must not be collapsed into a single verdict surface.
3. **Silent verdict freshness is a form of authority drift.**
   TTL must be explicit, not implicit-in-timestamp.
4. **Governor-absent must be a named state**, not an inferred one,
   or degraded operation becomes quiet lying.
5. **Low-standing evidence may ride a temporary opaque-hash bridge**
   only if marked as such at the receipt level, and only until the
   witness evidence type lands.
6. **Receipts must carry lineage.** Standing moves through a run;
   receipts must chain it. Minimum lineage:
   `finding ingest → packet proposal → transition authorization →
   action authorization`. Parent receipt IDs are required fields,
   not metadata. Four valid receipts with no shared story is the
   failure mode this prevents.

## Build Order

### Conceptual order (fidelity-first)
1. Witness evidence type + standing gate
2. `policy_id` resolver
3. `authorize_transition` + verdict TTL
4. Finding ingest bridge
5. Capability registry + degraded-mode contract
6. Approval queue RPC (agenda-scoped)

### Practical order (movement-first, recommended)
1. `policy_id` resolver
2. Degraded-mode contract
3. `authorize_transition` with TTL hooks (minimal)
4. Minimal finding ingest bridge (provisional)
5. Witness evidence type + standing gate
6. Capability registry cleanup
7. Approval queue RPC

**Practical order intentionally incurs epistemic debt until
`WitnessEvidence` lands.** Honest debt is fine. Hidden debt
becomes theology.

Provisional compromise for practical order: items 3–4 may carry
opaque-hash evidence *only if the receipt is explicitly marked
`evidence_class: low_standing_provisional`*. When item 5 lands, the
bridge is deprecated and migrated. This rule must be enforced in
code, not convention.

**Exit criterion**: no new evidence class may be introduced on the
provisional bridge after `WitnessEvidence` lands. Provisional has a
way of becoming "legacy, but forever" — this prohibition exists to
prevent that drift.

## Non-Goals

- Does not specify the wire format of the `policy_id` contract.
- Does not specify the NQ → Governor finding schema (needs its own
  design pass).
- Does not specify the reverse flow (Governor decisions closing NQ
  findings). NQ's `ACTION_OVERLAY_GAP` is still a stub; both sides
  of that contract need to be drafted together.
- Does not address Continuity coupling. NS treats Continuity as
  optional context (intelligence dependency, not safety dependency);
  Governor should not change that.
- Does not commit to a transport choice beyond reusing the existing
  daemon JSON-RPC.

## References

### Night Shift (`~/git/scheduler/docs/`)
- `DESIGN.md` — promotion ladder, authority model
- `GAP-governor-contract.md` — `check_policy` / `record_receipt` /
  `authorize_transition` sketch, degraded mode
- `GAP-escalation.md` — escalation triggers, Governor receipt with
  role `escalation`
- `GAP-mcp-authority.md` — seven MCP call-classes, stage+ gating
- `GAP-nq-nightshift-contract.md` — FindingSnapshot pull contract
- `GAP-nq-activation.md` — push/pull semantics, storm control

### NQ (`~/git/nq/docs/gaps/`)
- `FINDING_EXPORT_GAP.md` — canonical FindingSnapshot DTO
- `ACTION_OVERLAY_GAP.md` — stub, names Governor/WLP as substrate
- `STORAGE_BACKEND_GAP.md` — receipt durability contract
- `DASHBOARD_MODE_SEPARATION_GAP.md` — snapshots as evidence, not
  instrumentation

### nq-witness (`~/git/nq-witness/`)
- `SPEC.md` v0 — generic witness contract (schema, coverage, standing,
  freshness)
- `profiles/zfs.md` v0 — first profile, forcing case

### Adjacent Governor gaps
- `GOV_GAP_PROMOTION_SURFACE_001.md` — downgrade verdict, predicate
  trace, durability class (overlaps with §2 and §4 here)
- `GOV_GAP_RUNTIME_SUPERVISOR_001.md` — shipped intervention/promotion
  queues that item 7 reuses
- `GOV_GAP_DECISION_CONTEXT_001.md` — decision-time context closure,
  adjacent to verdict TTL
- `GOV_GAP_SCHEDULED_TASKS_001.md` — prior thinking on deferred work
