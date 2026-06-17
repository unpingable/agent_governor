I have everything I need. Here is the concrete plan — no files were edited.
---
# Design Plan: `capacity_refused` as an intelligible control signal
## 0. Key finding that drives the whole design (the load-bearing constraint)
`la_kind == "capacity_refused"` is **emitted from four distinct LA paths**, and the ratified mapping discipline says only **one** of them earns `new_authority_required`:
| Source | Location | ratified disposition |
|---|---|---|
| consume → `InsufficientCapacity` | `linear_accountant_client.py:816-829` | **`new_authority_required` / `current_grant`** ✅ |
| request-time `Denied` | `linear_accountant_client.py:683-698` | `unknown` (must NOT be guessed) |
| unknown `CapacityDecision` variant | `linear_accountant_client.py:700-710` | `unknown` |
| unknown `ConsumptionDecision` variant | `linear_accountant_client.py:853-865` | `unknown` |
**Therefore the disposition cannot be derived downstream from `la_kind`** (all four look identical there). It must be assigned at the one structural branch where `InsufficientCapacity` is unambiguous — inside `consume()`. Deriving it later by re-parsing `result.la_decision["decision"]` would re-implement that discrimination fragilely. This is the reason the edit lands in `linear_accountant_client.py`, not only in the supervisor.
A second consequence: the `no_session_grant` path in `lab_gate.py:162-167` sets `la_kind = self.grant_refusal`, which **can itself be `capacity_refused`** (a request-time `Denied` bubbling up). That path must default to `unknown` — it does so naturally because it never passes the new kwargs.
---
## 1. Where LA's decision becomes AG's worker-facing deny payload
Two hops:
1. **`linear_accountant_client.consume()`** (`linear_accountant_client.py:716-865`) maps the LA `ConsumptionDecision` → `RefusalResult(kind=…)`.
2. **`lab_gate.decide_write_effect()`** (`lab_gate.py:148-202`) wraps that `RefusalResult` → `LabEffectDecision`.
3. **`SessionSupervisor._handle_tool_proposed()`** (`supervisor.py:617-638`) turns `LabEffectDecision` into (a) the `TOOL_CALL_DENIED` **bus event** payload and (b) the `ControlAction(kind="deny", payload=…)` that `adapter.send_control` actually delivers **to the inner worker**. (b) is the worker-facing carrier (`supervisor.py:633-637`).
## 2. Are distinct LA refusal variants already preserved?
**Yes, for the non-`capacity_refused` variants** — `linear_accountant_client.py:836-851` already maps `Expired/Revoked/UnknownToken/ScopeMismatch` to their own closed kinds (`token_expired`, etc.) per the S4-lite ratification. Those reach the worker as distinct `la_kind` values.
**No, within the `capacity_refused` bucket** — the four sources above collapse to one `la_kind`. That collapse is exactly what blocks "retry later vs. authority exhausted," and it is preserved only inside the branch structure of `consume()` / `request_capacity()`, not in any field carried forward. The new fields fix this without splitting `capacity_refused` (acceptance §1).
## 3. Minimum schema-bearing object
**Do not introduce a new wrapper dataclass.** Extend the two existing AG-side result types with three fields each, plus a closed enum defined alongside the existing `CLOSED_REFUSAL_KINDS`. This matches the repo's closed-vocab idiom and adds no new "Kind" type (respects the module's forbidden-changes list — not an ArtifactKind/UseKind, not transport, not schema unification, not a base class, not an LA field rename).
New vocabulary (in `linear_accountant_client.py`, near line 124):
```python
RETRY_SAME_AUTHORITY     = "retry_same_authority"
RETRY_AFTER_DELAY        = "retry_after_delay"
NEW_AUTHORITY_REQUIRED   = "new_authority_required"
OPERATOR_ACTION_REQUIRED = "operator_action_required"
NEVER_RETRY              = "never_retry"
RETRY_UNKNOWN            = "unknown"          # default; NOT retry_after_delay
RETRY_DISPOSITIONS = frozenset({...all six...})
TERMINAL_SCOPE_CURRENT_GRANT = "current_grant"
CAPACITY_EXHAUSTED_MESSAGE = (
    "Write capacity for this grant is exhausted. "
    "Retrying under the same grant cannot succeed."
)
```
Carriers (defaults make every existing call site valid unchanged):
- `RefusalResult` (`:257`): `+ retry_disposition: str = RETRY_UNKNOWN`, `+ terminal_scope: Optional[str] = None`, `+ message: Optional[str] = None`.
- `LabEffectDecision` (`lab_gate.py:68`): same three fields, same defaults.
**Agreement enforced by construction** (acceptance §6) — extend `RefusalResult.__post_init__` (`:277-284`):
```python
if self.retry_disposition not in RETRY_DISPOSITIONS:
    raise ValueError(...)
if self.retry_disposition == NEW_AUTHORITY_REQUIRED:
    if not self.terminal_scope or not self.message:
        raise ValueError("new_authority_required requires terminal_scope and message")
```
This makes "machine fields and human text agree" a cheap falsifiable invariant rather than a convention.
Reaches the worker via: `consume()` sets the fields → `decide_write_effect()` copies them → supervisor writes them into both the bus event payload and the `ControlAction.payload` delivered by `send_control`.
## 4. Backward-compatibility implications
- All three new fields have defaults → every existing positional/keyword construction of `RefusalResult` and `LabEffectDecision` stays valid.
- `la_kind`/`reason` are **untouched**: existing tests pinning `payload["la_kind"] == "capacity_refused" | "already_consumed" | "consumed"` (`test_runtime_lab_gate.py:217,242,262`; `test_runtime_lab_gate_real_la.py:163-181`) keep passing (acceptance §1).
- The ratified schema's `reason` slot ≡ AG's existing **`la_kind`** (the stable machine token); the ratified `message` is the **new** key. I deliberately do **not** rename `la_kind`→`reason` or repurpose the existing prose `reason` key — that would break pins. The legacy prose `reason` key stays for back-compat; `message` is the authoritative human text. (Document this redundancy as accepted.)
- Bus/ControlAction payloads are free-form dicts (`bus.emit(payload=…)`), so added keys need no migration; consumers reading specific keys are unaffected.
- `__post_init__` is stricter, but only on the new field — defaults pass, so no existing construction newly raises.
## 5. Specific files + edits + tests
**Edit A — `src/governor/linear_accountant_client.py`**
- After `CLOSED_REFUSAL_KINDS` (~`:124`): add the six `RETRY_*` constants, `RETRY_DISPOSITIONS`, `TERMINAL_SCOPE_CURRENT_GRANT`, `CAPACITY_EXHAUSTED_MESSAGE`.
- `RefusalResult` (`:257-284`): add 3 fields after `parent_receipt_id`; extend `__post_init__` with the closed-enum check + agreement invariant.
- `_refuse()` (`:539-570`): add params `retry_disposition: str = RETRY_UNKNOWN, terminal_scope: Optional[str] = None, message: Optional[str] = None`; pass them into the `RefusalResult(...)` it builds. (All other callers omit → defaults.)
- `consume()` `InsufficientCapacity` branch (`:816-829`): the **only** call that passes `retry_disposition=NEW_AUTHORITY_REQUIRED, terminal_scope=TERMINAL_SCOPE_CURRENT_GRANT, message=CAPACITY_EXHAUSTED_MESSAGE`. Leave the request-time `Denied` (`:690`) and both unknown-variant fallthroughs untouched.
**Edit B — `src/governor/runtime/lab_gate.py`**
- `LabEffectDecision` (`:68-78`): add `retry_disposition: str = "unknown"`, `terminal_scope: Optional[str] = None`, `message: Optional[str] = None`.
- `decide_write_effect()` RefusalResult return (`:197-202`): copy `result.retry_disposition / .terminal_scope / .message` into the `LabEffectDecision`. The `no_session_grant` direct-construct path (`:162-167`) is left defaulting to `unknown`/`None`.
**Edit C — `src/governor/runtime/supervisor.py`**
- Deny block (`:618-637`): add `"retry_disposition": decision.retry_disposition`, `"terminal_scope": decision.terminal_scope`, `"message": decision.message` to **both** the `TOOL_CALL_DENIED` bus payload (`:622-630`) and the worker-facing `ControlAction(kind="deny", …).payload` (`:634-637`). Keep existing `reason`/`la_kind` keys.
**Tests to add**
- `tests/test_linear_accountant_client.py` (unit, where the discrimination lives):
  1. `InsufficientCapacity` → `kind==capacity_refused`, `retry_disposition==new_authority_required`, `terminal_scope=="current_grant"`, `message==CAPACITY_EXHAUSTED_MESSAGE`.
  2. **Discrimination guard** (acceptance §4): request-time `Denied` → `kind==capacity_refused` **but** `retry_disposition==unknown`, `terminal_scope is None`. Proves the bucket isn't blanket-assigned.
  3. unknown `ConsumptionDecision` variant → `capacity_refused`, `retry_disposition==unknown`.
  4. `AlreadyConsumed`, `token_expired`, `scope_mismatch`, `unknown_token`, `token_revoked` → each `retry_disposition==unknown`, `terminal_scope is None`, `message is None` (acceptance §4/§5).
  5. `__post_init__` rejects an out-of-set `retry_disposition`; rejects `new_authority_required` with missing `terminal_scope`/`message` (acceptance §6 — the agreement invariant).
  6. Serialization/back-compat (acceptance §7): `dataclasses.asdict(RefusalResult(kind="already_consumed", detail="x"))` yields `retry_disposition=="unknown"`, `terminal_scope is None`; constructing without the new args still works.
- `tests/test_runtime_lab_gate.py` (integration on the real supervisor path):
  7. Extend `test_exhausted_grant_refuses_before_effect` (or add a sibling): each denied payload has `retry_disposition=="new_authority_required"`, `terminal_scope=="current_grant"`, `message==CAPACITY_EXHAUSTED_MESSAGE`; assert the same three keys appear on the worker-facing `deny` `ControlAction.payload`.
  8. Extend `test_replay_proposal_refused_already_consumed`: denied payload `retry_disposition=="unknown"`, `terminal_scope is None`.
  9. `no_session_grant` path (token never acquired, e.g. request-time `capacity_refused` grant refusal): deny payload `retry_disposition=="unknown"` — proves a *grant-time* capacity refusal does NOT inherit `new_authority_required`.
**Acceptance coverage:** §1 (la_kind/reason untouched), §2 (InsufficientCapacity terminal+new_authority via test 1/7), §4 (tests 2/4), §5 (default `unknown`, tests 3/4/8/9), §6 (`__post_init__` invariant, test 5 + same-branch single source), §7 (serialization tests 6 + pinned payloads 7/8), §8 (no edit to LA policy or P4 — none of the above touches LA's contract fields, `ActiveTunableStore`, or P4). §3 is the live-worker validation deferred by the spec; the field is present and authoritative on the worker-facing `ControlAction.payload`.
**Out of scope / not touched:** LA contract field names, `CookedConsumeRequest`/`CookedCapacityRequest`, the closed `CLOSED_REFUSAL_KINDS` set (no `capacity_refused` split), `ActiveTunableStore`, P4, and the existing positive (`consumed`/`granted`) receipt paths.
---
STOP — read-only pass complete; no edits, commits, or pushes made.