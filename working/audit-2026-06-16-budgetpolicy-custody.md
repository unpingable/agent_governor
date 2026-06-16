# Audit — `BudgetPolicy` custody (read-only)

**Date:** 2026-06-16
**Mode:** read-only custody trace. No config-path changes.
**Prompt:** post-P4-PARKED follow-up — "audit one *existing live* actuator's
custody, not the dormant activation framework." Candidate proposed (ChatGPT):
`BudgetPolicy`.
**Verdict:** negative result of a useful kind. `BudgetPolicy` is a *partial*
live actuator with weak custody — and that weakness is **already named, ruled
on, and fenced** (`working/post-mvp-debt-ba3-hardshort-to-la.md`), not a fresh
discovery. **Do not open a "BudgetPolicy custody" campaign.** Two small in-scope
completeness sub-findings added below.

## Surface

`src/governor/runtime/budget.py` — `Spend`, `BudgetLimit`, `BudgetPolicy`,
`BudgetViolation`, `StepSpend`, `RunBudgetLedger`, `default_budget_policy()`.
Consumed only by the Runtime Supervisor (`src/governor/runtime/supervisor.py`).

## Seven custody questions

1. **Who constructs / can mutate it.** Operationally: nobody but the hardcoded
   `default_budget_policy()` (budget.py:207 — 500k tokens / 100 tool_calls /
   50 remote_calls / 200 steps). The sole injection point is
   `policy_context["budget_policy"]` (supervisor.py:294), plumbed through
   `create_session → fork → launch`. **But neither operator surface populates
   it** — daemon RPC `runtime.session.create` (daemon.py:3390) and CLI
   `runtime launch` (cli.py:19964) both omit `policy_context`. So every
   supervised session in practice runs the hardcoded default. The only way to
   set a custom budget is the in-process Python API. No operator-facing
   mutation path exists.

2. **Resolution: once per run or opportunistic.** Once, at `create_session`
   (supervisor.py:294-300); resolved into the facet and never re-read. Fork
   inherits parent's `policy_context` by value. Clean.

3. **Which production path consumes it.** Live gate: `_handle_tool_proposed`
   (supervisor.py:534-559) projects `spend + Spend(tool_calls=1)`, calls
   `would_breach_hard`, and on a hard violation emits `TOOL_CALL_DENIED`
   (`SourceLayer.POLICY`) **and** sends a `deny` control to the adapter. This
   is a genuine actuator — it blocks tool calls. Also `_record_step_spend`
   (post-hoc) and `get_budget` (reporting). **The drill/demo/spine path does
   NOT wire it** (drill_poster.py:44-54 — "the runtime supervisor never wires
   them into the drill path").

4. **Observable behavior between two values.** Lowering `tool_calls` denies a
   supervised agent sooner — that dimension actuates. **BUT three of the four
   default limits are structurally inert:** `_record_step_spend` always records
   `Spend(tool_calls=1)` with `provider_kind="local"`, so `total_tokens` /
   `usd_micros` / `latency_ms` stay `None` forever and `remote_calls` stays `0`.
   `BudgetPolicy.check` skips `None` dimensions (`if actual is None: continue`,
   budget.py:105-106). **The headline 500k-token limit can never fire; the
   50-remote-calls limit can never fire.** Only `tool_calls` (100) and
   `max_steps` (200) are live, and they co-increment, so `tool_calls` binds
   first. Changing the token budget produces **no** observable behavior change.

5. **Bound to a run / config identity.** Weakly. The ledger carries `policy_id`
   (freeform string, "default") + `session_id`. No content hash of the policy;
   `policy_id` is a label, not a binding (two distinct policies can both be
   "default"). Spend decisions are logged as canonical **EventBus events**
   (`TOOL_CALL_DENIED` / `budget_exhausted` / `budget_ledger`), **not**
   content-addressed `GateReceipt`s — there is no `GateReceipt` / `ReceiptStore`
   import anywhere in `runtime/`. The policy is not hash-pinned to the run.

6. **Stale / malformed / conflicting → fail closed?** Mixed. `from_dict` raises
   on bad keys (`BudgetLimit(**l)`) — but is never called operationally. The
   operative failure mode is **fail-open-by-unmeasurement** (Q4): unmeasurable
   dimensions are silently skipped. No "conflicting sources" risk (single
   hardcoded source). *Lower-confidence flag:* in `_handle_tool_proposed` the
   `deny` only reaches the backend if `facet.handle` is set (supervisor.py:554);
   otherwise the denial event is emitted but no control reaches the adapter.
   Presumed benign (handle set while running) — noted as a question, not an
   assertion.

7. **Receipt claiming more custody than exists?** Drill/demo surface does **not**
   overclaim — budget guards render as `bypass_ag_rcpt_<not_minted>` honest-
   absence placeholders (drill_poster.py:44-54), and the debt file is loud that
   this is noncanonical. Narrower overclaim: **`get_budget` (RPC
   `runtime.budget.get`) returns a `policy` advertising a 500k-token /
   50-remote-call limit the system structurally cannot enforce** — an operator
   reading it sees enforcement that does not exist.

## Why this is NOT a new campaign

The custody weakness is the *documented MVP posture*, not a discovery:

- `working/post-mvp-debt-ba3-hardshort-to-la.md` already classifies
  `RunBudgetLedger` as a **BA3 internal budget guard** to be hard-shorted to
  Linear Accountant so AG carries **zero authoritative budget surfaces**
  post-MVP.
- That file explicitly forbids the move ChatGPT's framing would invite:
  *"Not authorization to start replacing BA3 surfaces today. RunBudgetLedger
  replacement before LA wires would create a capacity-shaped hole."*
- Parent invariant: `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md`.

So the recommended outcome "live actuator + weak custody → legitimate new
campaign" does **not** apply: the campaign already exists, is parked behind the
LA-wiring trigger, and is fenced against premature start. This audit *confirms
the debt file is accurate* and adds two findings it doesn't explicitly carry.

## New sub-findings (in-scope completeness candidates — NOT a campaign)

- **F1 — token limit is structurally inert.** `default_budget_policy()`
  advertises a 500k-token (and 50-remote-call) hard limit that can never fire
  because the supervisor never measures token/remote spend for local tool
  steps. Either measure it or drop the dead limits from the default.
- **F2 — `get_budget` reporting overclaim.** `runtime.budget.get` surfaces
  unenforceable limits as live policy. Smallest honest fix: mark limits whose
  dimension is never measured on the current path (or omit them from the
  reported policy).

Both are localized doc/reporting honesty items; neither requires touching the
spendability authority and neither is blocked on LA. File-but-don't-build until
the BA3 debt is paid, OR fold F2 into the LA hard-short when it lands.

## Next candidate if another live-actuator audit is wanted

Not routing (`BudgetManager`) — same BA3 class, same parked debt. A genuinely
*different* live actuator outside the spendability family would be needed to
test the "where does operational control get its authority today" question on
fresh ground.
