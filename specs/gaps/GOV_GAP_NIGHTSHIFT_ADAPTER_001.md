# GOV_GAP_NIGHTSHIFT_ADAPTER_001

## Title
Night Shift Governor Adapter: thin RPC surface bridging NS daemon expectations to existing governor primitives

## Status
Gap spec — 3.x (new wire-facing adapter, not a 2.x feature).

## Origin

Night Shift (~/git/scheduler) declared the expected adapter shape
at `~/git/scheduler/docs/GAP-governor-contract.md` on 2026-04-16
(observatory-family `mem_42cc0383e146473b8099b3bde66d4197`). The
contract has been sitting for ~a week as an open next_action. The
2026-04-23 tolerability-horizon dogfood pass identified Night Shift
as the first natural consumer ("meaningfully worse without
Governor") and this adapter is the forcing function.

Night Shift confirmed 2026-04-23 that bounded prep is in place on
its side (horizon.rs with action_for + lineage path) and is
holding on governor Commit B before starting the second dogfood
pass. This gap spec is Commit B's design artifact.

## Problem Statement

Night Shift is loosely coupled to Governor at the code boundary
and tightly coupled at the protocol boundary. The protocol
boundary does not yet exist. Without it:

- Night Shift cannot promote above `advise` (contract fail-closed
  invariant: never assume permission when Governor is silent).
- The reconciler cannot wire end-to-end against the real governor
  surface; it has to stub with fake-governor calls that harden in
  ways that will diverge from the real shape.
- Commit A's horizon primitives cannot cash out into a working
  four-way distinction (expired_tolerance / tolerated_active /
  basis_invalidated / fresh_arrival) because the reconciler depends
  on the adapter for policy/receipt/transition flow.

The adapter is the minimum surface that unblocks Night Shift's
reconciler wiring and the second dogfood pass.

## Non-goals

- **Not a new policy engine.** `policy_engine.evaluate` is
  authoritative; the adapter translates NS's request shape to
  `PolicyEvalRequest` and back.
- **Not a Night Shift implementation.** Rust-side reconciler
  wiring lives in `~/git/scheduler` per the cross-repo discipline
  (feedback_cross_repo_pm).
- **Not a general multi-consumer adapter.** Scoped to Night
  Shift's declared shape. Future consumers may motivate a
  different factoring.
- **Not a replacement for existing `policy.*` RPC.** Those remain
  for direct policy evaluation. The `nightshift.*` methods are
  thin higher-level wrappers carrying NS-specific vocabulary
  (authority levels, event kinds, blast radius, etc.).

## Existing Governor Coverage

### Direct mappings (already in place)

| NS need | Governor primitive |
|---|---|
| Policy evaluation | `policy_engine.evaluate(PolicyEvalRequest, PolicyRuleSet) → PolicyEvalResult` |
| Obligation vocabulary | `policy_engine.ObligationKind` — covers all 5 NS-requested obligations verbatim |
| Receipt emission | `GateReceiptSystem.emit(...)` — content-addressed, role-parameterized |
| Receipt roles | `ROLE_MEASUREMENT`, `ROLE_PROPOSAL`, `ROLE_AUTHORITY`, `ROLE_RECOVERY_PLAN` — all four NS roles present |
| Transport framing | JSON-RPC over stdio/unix socket, Content-Length framing — NS spec explicitly matches governor daemon shape |
| Receipt content hash | `subject_hash`, `evidence_hash`, `policy_hash` — all three carried by NS event payload |

### Partial / extension

| NS need | Status |
|---|---|
| Capability vocabulary | 5/8 present: READ_FS, WRITE_FS, EXEC, NETWORK_EGRESS, REPO_WRITE, CONFIG_WRITE; missing MCP_CALL, NIGHTSHIFT_PROMOTE, PAGE_HUMAN |
| Verdict vocabulary | Different: policy_engine is `pass/block/escalate/warn`; NS expects `allow/deny/require_approval/downgrade` |

### Genuinely absent

- Authority-level closed enum (observe / advise / stage / request /
  apply / publish) — NS-specific
- Event-kind closed enum (agenda.promoted / action.authorized /
  action.applied / action.denied / action.verified /
  escalation.paged) — NS-specific
- Blast-radius closed enum (single_host / multi_host / public) —
  NS-specific
- Tool-class closed enum (read / propose / stage / mutate /
  publish / page) — NS-specific
- Action-kind closed enum (mcp_call / tool_exec / state_mutation /
  publish) — NS-specific
- Three `nightshift.*` RPC methods

## Design

### A1 — Capability vocabulary extension

Add three values to `policy_engine.Capability`:

- `MCP_CALL` — `"mcp_call"`
- `NIGHTSHIFT_PROMOTE` — `"nightshift_promote"`
- `PAGE_HUMAN` — `"page_human"`

Placed alongside existing domain-specific capabilities (POLICY_OVERRIDE,
APPROVAL_CONSUME, HANDOFF_REMOTE). Minor pollution of the general
vocabulary is accepted; the alternative (adapter bypassing
strict_taxonomy) destroys the closed-set discipline.

### A2 — Adapter module: src/governor/nightshift_adapter.py

Closed enums (frozen v1):

```
AuthorityLevel: observe / advise / stage / request / apply / publish
BlastRadius:    single_host / multi_host / public
ToolClass:      read / propose / stage / mutate / publish / page
ActionKind:     mcp_call / tool_exec / state_mutation / publish
EventKind:      agenda.promoted / action.authorized / action.applied /
                action.denied / action.verified / escalation.paged
NightShiftVerdict: allow / deny / require_approval / downgrade
```

Dataclasses (frozen):

- `RequestedAction(kind, tool_class, tool_id, arguments_hash,
  blast_radius, reversible)`
- `CheckPolicyRequest(agenda_id, run_id, actor, requested_action,
  bundle_ref, authority_level)`
- `CheckPolicyResponse(verdict, reason, obligations, downgrade_to,
  receipt_id)`
- `RecordReceiptRequest(event_kind, run_id, agenda_id, from_level,
  to_level, subject_hash, evidence_hash, policy_hash)`
- `RecordReceiptResponse(receipt_id, receipt_hash)`
- `AuthorizeTransitionRequest(run_id, agenda_id, from_level,
  to_level, evidence_summary)`
- `AuthorizeTransitionResponse(verdict, reason, required_approvals,
  receipt_id)`

Verdict mapping (policy_engine → NS):

- `PASS` → `allow`
- `BLOCK` → `deny`
- `ESCALATE` → `require_approval`
- `WARN` → `downgrade` (default `downgrade_to = advise`)

Three adapter functions:

```
check_policy(request: CheckPolicyRequest, state) -> CheckPolicyResponse
record_receipt(event: RecordReceiptRequest, state) -> RecordReceiptResponse
authorize_transition(request: AuthorizeTransitionRequest, state) -> AuthorizeTransitionResponse
```

Each function:

1. Validates input (closed enums, required fields) — raises
   ValueError on bad input (caller-side problem, not a verdict).
2. Bridges to existing primitives:
   - `check_policy` → `policy_engine.evaluate` + emit gate receipt
     with `role=measurement` and policy_check subject kind
   - `record_receipt` → `GateReceiptSystem.emit` with role derived
     from event_kind (authorized/applied → `authority`;
     denied/verified → `measurement`; promoted → `authority`;
     paged → `measurement`)
   - `authorize_transition` → `policy_engine.evaluate` with
     transition-specific request shape + emit receipt with
     `role=authority`
3. Returns the NS-shape response.

### A3 — Fail-closed discipline

Per NS contract fail-closed invariants:

- Missing required request fields → `ValueError` (caller sees RPC
  error). Not a silent default.
- Unknown enum values → `ValueError` with closed-set enumeration.
- Governor can always produce a receipt_id. A deny verdict does
  not skip the receipt — the denial itself is recorded.
- Transport-level failures (not this module's concern) propagate
  as JSON-RPC errors; NS treats missing response as deny per its
  contract.

### A4 — Daemon RPC registration

Three handlers in `daemon.py`:

```
dispatcher.register("nightshift.check_policy", nightshift_check_policy)
dispatcher.register("nightshift.record_receipt", nightshift_record_receipt, mutating=True)
dispatcher.register("nightshift.authorize_transition", nightshift_authorize_transition, mutating=True)
```

`check_policy` is read-only (pure evaluation, no state mutation
beyond the receipt side-effect which is part of every gate call).
`record_receipt` and `authorize_transition` are marked mutating
because they always emit a receipt regardless of verdict.

Update `EXPECTED_METHODS` list in tests and bump
`test_rpc_method_count` assertion from 88 to 91.

### A5 — Horizon interaction

The adapter is aware of `receipts.horizon_expiring_soon` from
Commit A but does not wrap or re-expose it — Night Shift's
reconciler calls horizon RPC directly. This adapter is about
policy / receipts / transitions, not about horizon lineage.
Horizon flows through `record_receipt` naturally: NS-emitted
receipts may carry a HorizonBlock in the request, which the
adapter forwards into the GateReceipt.

For the second dogfood pass: NS receives governor-emitted receipts
via `check_policy` responses (evidence_hash / policy_hash /
receipt_id), queries `receipts.detail` or
`receipts.horizon_expiring_soon` as needed, and persists local
`AttentionState::WatchUntil` state per the A5 persistence
obligation from `GOV_GAP_TOLERABILITY_HORIZON_001`.

## Module Touchpoints

- `src/governor/nightshift_adapter.py` — new module (~500 lines)
- `src/governor/policy_engine.py` — 3 new Capability values
- `src/governor/daemon.py` — 3 new RPC handlers + registrations
- `tests/test_nightshift_adapter.py` — new test file
- `tests/test_daemon.py` — add `TestNightShiftAdapter` class,
  update EXPECTED_METHODS list + method count

## Invariants

1. **Verdict mapping is deterministic.** Each `PolicyVerdict` maps
   to exactly one `NightShiftVerdict`. No runtime policy can
   change the mapping.
2. **Every adapter call emits a receipt.** Deny, allow,
   require_approval, downgrade — all produce a receipt_id. A
   missing receipt is a bug.
3. **Enum values are closed.** Adding a value requires a gap-spec
   supersession.
4. **Adapter is translation only.** No new policy logic; always
   delegates to `policy_engine.evaluate` or
   `GateReceiptSystem.emit`.
5. **Fail-closed on missing/malformed inputs.** Unknown enum,
   missing required field → ValueError. NS's contract requires
   deny-on-silence; this is the in-process analog.
6. **Horizon is orthogonal.** The adapter does not invent horizon
   semantics; it forwards HorizonBlock into receipts when present.

## Open Questions

1. **Obligation surface on the wire.** NS spec shows obligations
   as bare strings (`[record_receipt, log_high_priority, ...]`).
   Governor's `ObligationKind` is richer (kinds + details). For
   v1 wire format, emit just the `.kind.value` strings — NS can
   request structured obligations in a later version.
2. **"record_receipt" as an obligation name.** NS lists
   `record_receipt` in the obligations array. That isn't in
   `ObligationKind` — it's a procedural instruction ("you must
   call record_receipt() next"). For v1 the adapter injects it
   when check_policy emits a receipt the caller should follow up
   on. Alternative: treat it as implicit (every allow requires
   record_receipt follow-up). Going with implicit for v1; NS can
   request explicit listing later.
3. **Dry-run mode.** NS spec §Open Questions mentions
   `check_policy` with `dry_run: true` for agenda capture-time
   misconfiguration detection. Not in v1; add as Open Question
   here too.
4. **Capability-listing RPC.** NS spec mentions potentially
   fetching governor's capability vocabulary dynamically. Governor
   already has `policy.capabilities` RPC (existing). NS can call
   it; no new surface needed.
5. **Transport.** v1 uses existing daemon JSON-RPC (stdio /
   Unix socket / Content-Length framing). Matches NS contract
   spec preference. No new transport layer.
6. **Policy resolution (agenda → policy_id).** NS spec §Open
   Questions: who owns the binding. For v1 the agenda declares
   `policy_id` in the request and governor's PolicyRuleSet uses
   it. Future work may add a policy-resolution RPC.

## Acceptance criteria

- [ ] `nightshift_adapter` module exports the three functions, all
      enums closed, all request/response dataclasses with
      to_dict/from_dict.
- [ ] All four `PolicyVerdict` values map to the correct
      `NightShiftVerdict` value; covered by explicit test.
- [ ] Each adapter function emits a gate receipt with the correct
      receipt_role per design A2.
- [ ] Three daemon RPC methods registered, callable, return
      well-formed JSON-RPC 2.0 responses for positive inputs.
- [ ] `EXPECTED_METHODS` extended with the three new names.
- [ ] `test_rpc_method_count` assertion bumped to 91.
- [ ] Pre-existing standing.py shadow bug remains the only source
      of error-path test failures; positive paths pass.
- [ ] `MCP_CALL`, `NIGHTSHIFT_PROMOTE`, `PAGE_HUMAN` accepted by
      `policy_engine.evaluate` with `strict_taxonomy=True`.

## Relationship to other gaps

- **GOV_GAP_TOLERABILITY_HORIZON_001** (A5 persistence obligation):
  the adapter carries HorizonBlock forward via record_receipt when
  NS supplies it. Horizon-expiring-soon remains a direct RPC; the
  adapter doesn't wrap it.
- **GOV_SPEC_POLICY_001 / GOV_SPEC_CAP_001 / GOV_SPEC_OBL_001:**
  the underlying canonical specs for policy/capability/obligation
  vocabularies. The adapter extends Capability (A1) and uses the
  existing Obligation vocabulary unchanged.
- **feedback_cross_repo_pm** (auto-memory): the cross-repo
  discipline — in-repo notes, no drafting for the scheduler repo.
  This spec is agent_gov-side only.

## Compressed line

> Governor's adapter is translation, not policy. The protocol boundary is thin because the primitives are real.
