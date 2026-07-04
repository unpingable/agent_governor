# Governed Playbooks — Slice 7 exit ticket (allowlist slice)

**Done 2026-06-25** (gov loop, branch `feat/playbooks-gov-loop`). Ration-card dispatch of one
**live external agent** — the *allowlist* slice, NOT bounded autopilot. A governed playbook may
dispatch ONE named external agent to perform ONE predeclared boring task under a brutally narrow
ration card, with fresh admission + durable spend, producing only non-authoritative receipts.
Files: `src/governor/playbooks/ration_card.py` (new), `tests/test_ration_card_dispatch.py`
(13 tests). Playbooks regression: **142 passed, exit 0**.

## The boss fight, pinned

> A live external agent is dispatched once, under fresh governed admission and durable spend,
> produces an inert report, and CANNOT convert its report, transcript, or success into authority
> for a second action.

`dispatch_under_ration_card` runs the agent exactly once (via an injected `RationedAgentRunner`),
only after the full Slice 3–5 chain spends, and emits a `verdict=observe` dispatch report that
carries the transcript as a **digest** (never the raw text as a claim) and fails
`is_authority_admission_receipt`. The transcript, the success flag, and the report are all
structurally inert.

## The laundering walls (these got more tests than the happy path)

| Wall | Mechanism | Test |
|------|-----------|------|
| agent transcript ≠ authority | report is observe + transcript reduced to digest + fails authority predicate | `test_transcript_and_success_and_report_are_not_authority` |
| agent success ≠ authority | success flag lives in an observe report; never a spend basis | same |
| report ≠ authority | (S6) observe, `non_authoritative`, fails predicate | same |
| dispatch receipt ≠ permission to dispatch again | a 2nd dispatch needs a fresh spend; durable gate refuses replay → `DispatchNotRun`, runner not called | `test_dispatch_receipt_is_not_permission_to_dispatch_again` |
| allowlist membership ≠ Standing grant | carded request + no Standing → chain refuses at wicket, agent never runs | `test_allowlist_membership_is_not_standing_grant` |
| Standing grant ≠ LA spend | (S4) Standing pass + LA denied → no spend → no dispatch | `test_standing_grant_is_not_la_spend` |
| LA spend ≠ arbitrary tool access | out-of-card request refuses BEFORE any spend; card is a separate necessary gate | `test_la_spend_is_not_arbitrary_tool_access` |
| even the agent's output is fenced | actual writes checked ⊆ card; over-reach refused after the fact, no report minted | `test_agent_writing_outside_card_is_fenced_after_the_fact` |
| human refusal wins | kill switch consulted first, refuses before any spend | `test_human_refusal_wins_before_any_spend` |

## Tiny door, big lock — the ration card

`RationCard` is absence-restrictive (allowlist, not blocklist): a write path / shell command not
listed is forbidden; a novel one is refused, never admitted. The dangerous axes are **locked closed
by type** — `__post_init__` refuses a card that allows git, doctrine writes, network, or non-observe
output (`test_card_refuses_dangerous_axes`). You cannot *construct* a card that opens them in this
slice. The request is matched against the card (agent + task exact, writes/shell ⊆ allowlist,
network/git unrequested); out-of-card refuses.

The order encodes the walls: **human refusal → ration card → governed chain (spend) → dispatch once
→ fence the agent's output → non-authoritative report.** Refusal and card both gate *before* any
spend, so an out-of-card or vetoed dispatch never costs a spend.

## Did Slice 7 touch supervisor.py? — NO. Here is the call, and why it's right.

The operator's framing: "S7: external agent finally makes supervisor the right surface… but I would
NOT start S7 by making the supervisor understand playbooks generally. Make it understand ONE ration
card. Tiny door, big lock."

So this slice builds the **one ration card**, not a supervisor-playbook bridge. It dispatches the
external agent through a narrow `RationedAgentRunner` contract — the minimal "run this constrained
task once, return a result" surface that a real `runtime.RuntimeAdapter` (the supervisor's
external-agent abstraction, `claude_code.py` / `gemini_cli.py`) satisfies. The runner is **injected**
so the gate is deterministically testable; the live binding (a thin adapter that does
launch → drive the one task to completion → collect transcript → shutdown) is the remaining
production wiring, named here, **not** built into the gate.

This is deliberately NOT a `SessionSupervisor` (1337 lines, divergent machinery: continuation
grants, transition-kernel route, budget ledgers, present/burn C3) integration. Bloating it to
"understand playbooks" is exactly what the operator forbade. The ration-card gate is the tiny door
the supervisor would carry; wiring the live adapter into it (and, if desired, routing through
`SessionSupervisor`) is a follow-on with its own narrow forcing case.

**What remains for "real" S7 / bounded autopilot:**
1. **Live-adapter binding** — a thin `RationedAgentRunner` over `runtime.adapters.claude_code` that
   launches a real one-shot Claude Code run constrained to the card and collects its transcript.
   (Mechanical; the gate contract is fixed.)
2. **Bounded autopilot loop** — the open-loop version, still one-dispatch-per-iteration, each
   requiring fresh Wicket admission + LA spend + durable spend, Standing grants scoped and expiring,
   failures producing receipts. This slice deliberately does NOT loop.

## The non-collapse ladder, complete

S3 observe≠pass · S4 pass≠spend · S5 spend≠execution & durability≠permission · S6 report≠authority ·
**S7 dispatch≠authority** (transcript / success / report / dispatch-receipt none of them mint
authority for a next action; allowlist membership is not Standing; a spend is not arbitrary tool
access).

## Intentionally NOT done (stop line held)

- No `SessionSupervisor` edit; no live-adapter binding (injected runner only); no autopilot loop.
- No card that opens git / doctrine / network / non-observe output (locked by type).
- No raw transcript in any receipt (digest only); no discretionary task selection; no remembered may.

## Next possible slice (do NOT start without operator go)

The live-adapter binding (item 1 above) is the smallest real-runtime follow-on, and bounded
autopilot (item 2) is the loop. Both need operator go and, per the original S7 note, a fresh-eyes
pass on the allowlist before AG drives a real external agent against anything beyond a sandbox.
