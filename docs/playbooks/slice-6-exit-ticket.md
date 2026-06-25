# Governed Playbooks — Slice 6 exit ticket

**Done 2026-06-25** (gov loop, branch `feat/playbooks-gov-loop`). First self-hosted
governed-playbook chore — **dogfood execution, not autopilot**. AG runs ONE aggressively boring
read-only audit through the full Slice 3–5 chain and emits a non-authoritative report receipt.
Files: `src/governor/playbooks/chore.py` (new), `tests/test_governed_chore.py` (6 tests).
Playbooks + orchestrator regression: **178 passed, exit 0**.

## The chore chosen

**A read-only audit of the gate-receipt store → a non-authoritative report receipt.** The toaster:
`read_only_receipt_audit(sink)` tallies receipts by `(gate, verdict)`. It mutates nothing, decides
nothing, authorizes nothing. (The operator's pick: a read-only audit, not "refresh a generated
ledger" — a ledger is "a toaster with opinions." This is the plain toaster.)

## The boss fight, pinned

> AG runs a governed chore, leaves receipts, and a future AG cannot mistake the report for authority.

`run_governed_chore` runs the chore **only after** the full chain spends, then emits a structurally
inert report:
- `verdict="observe"` under its own gate `governed_chore_report` (it decides nothing),
- carries `non_authoritative: True` + `record_kind: chore_report`,
- **fails `is_authority_admission_receipt`** (gate≠wicket_seam / verdict≠pass) — so the Slice-4
  spend-basis wall already refuses it as a basis. A future AG cannot launder the report into
  authority. (`test_chore_runs_and_report_is_non_authoritative`.)

It cites the LA consume receipt as parent, so `governor why` walks report → consume → grant →
admission → standing.

## Dispatch gating (every invariant pinned)

The chore dispatches IFF the chain actually **spent** (`ChainResult.consumed`). A refusal anywhere
upstream returns `ChoreNotRun` and the chore never executes:

| Attempt                              | Result            | Test |
|--------------------------------------|-------------------|------|
| observe evidence receipt as trigger  | not a spend → no dispatch | (structural: chore gates on `consumed`) |
| Wicket pass but LA denies (no spend) | `ChoreNotRun` @ `la_seam_request` | `test_la_denied_does_not_dispatch` |
| no Standing                          | `ChoreNotRun` @ `wicket_seam` | `test_no_standing_does_not_dispatch` |
| durable spend, incomplete binding    | `ChoreNotRun` @ `playbook_durable_spend_seam` | `test_unbound_durable_spend_does_not_dispatch` |
| replay of the same chore             | `ChoreNotRun` (durable gate refuses) — no re-execute, no second report | `test_replay_does_not_re_execute_the_chore` |
| chore raises                         | `ChoreResult(ok=False)` — recorded, not folklore | `test_raising_chore_records_failure` |

Replay safety is **inherited, not re-implemented**: the Slice-5 durable spend gate refuses a
replayed spend, so the chore can't re-execute. The durable spend IS the chore's idempotency.

## The fifth non-collapse

Slices 3–5 made four non-collapses mechanical (observe≠pass, pass≠spend, spend≠execution,
durability≠permission). Slice 6 adds the fifth: **report ≠ authority.** A generated report records
what was observed; it never authorizes anything, and the existing authority predicate proves it.

## Did Slice 6 force the Track A supervisor pickup? — NO, and here is the principled reason

The operator framed Slice 6 as "where supervisor dispatch may finally earn its forcing case." It did
not — **because a self-hosted chore is the wrong shape for the supervisor.**

`runtime/supervisor.py` supervises **external agent runtimes** — it intercepts the tool calls of a
live Claude Code / Gemini CLI *agent session* (the `runtime/adapters/` are `claude_code.py`,
`gemini_cli.py`). A self-hosted chore is **AG's own code** (a read-only Python audit function); there
is no external agent, no tool-call stream to intercept. So the minimal dispatch path for a
self-hosted chore is a small executor that calls the chore function after the governed chain spends
— **not** a supervisor route. Touching `supervisor.py` here would have been the "while I'm here"
cleanup the stop line forbids.

This is the **fourth** time the Track A supervisor watch held — each for a distinct, principled
reason:
- S3: evidence coherence is decidable upstream of authority.
- S4: the spend *shape* is expressible through the existing LA seam.
- S5: durability crosses via a new gate (no `activate()`/supervisor edit).
- **S6: a self-hosted chore is not an external-agent dispatch.**

The supervisor's genuine forcing case is the **external-agent** case: when AG drives a *live external
agent* (Claude Code / Gemini) to do work, and that agent's tool calls must route through the governed
evidence→authority→spend→durable chain. That is **Slice 7 (bounded autopilot)** — the agent gets a
ration card, and the supervisor is finally the right surface because there is finally an external
agent to supervise.

## Why this is dogfood execution, not autopilot

- Exactly ONE chore, caller-supplied. No loop, no discretionary task selection, no "remembered may."
- The chore is read-only and its output is non-authoritative. No doctrine edit, no merge, no commit,
  no branch mutation — none are reachable from a read-only audit.
- Every run still passes through fresh evidence + authority + spend + durable gates; the chore has no
  standing of its own. It cannot self-perpetuate.

Autopilot (Slice 7) is the open-loop version *with a ration card*: AG may propose+execute only from a
tiny allowlist, every run requires fresh Wicket admission, every effect requires an LA spend, Standing
grants are scoped and expiring, failures produce receipts not retries-in-the-mist.

## Read-only contract + effect-bearing chores (named limit)

The chore is read-only **by contract** — the executor emits a receipt of the findings and applies no
mutation. Python cannot truly sandbox a callable, so "read-only" is a property of the *chosen* chore,
not an enforced cage. A chore with real (operational) effect MUST route its outcome through
`confer_operational_effect` (Wall 1) and therefore requires `OperationalConsumed` (observed origin);
a read-only report confers no operational effect, so the mechanical `consumed` gate is correct and
sufficient here. The harness runs under `stub_origin` (→ `DemonstratedConsumed`), which is honest:
this is a demonstration of structure, and a read-only report is exactly the kind of thing a
demonstration may produce.

## Intentionally NOT done (stop line held)

- No `supervisor.py` edit, no external-agent dispatch, no autopilot loop.
- No doctrine edit / merge / commit / branch mutation reachable from the chore.
- No generalized executor framework; `run_governed_chore` runs ONE chore and returns.

## Next possible slice (do NOT start without operator go)

**Slice 7 — bounded autopilot** (the ration card): AG drives a *live external agent* from a tiny
allowlist, each run requiring fresh Wicket admission + LA spend + durable spend, Standing grants
scoped and expiring, failures producing receipts. This is where `supervisor.py` is finally the right
surface, with the external agent as the forcing case.
