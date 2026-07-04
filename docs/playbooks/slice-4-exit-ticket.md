# Governed Playbooks — Slice 4 exit ticket

**Done 2026-06-25** (gov loop, branch `feat/playbooks-gov-loop`). Playbook-governed
**spend**: evidence → authority → LA capacity consume, no laundering. Files:
`src/governor/cooked_context_orchestrator.py` (optional `playbook_evidence` routing + the
authority-admission-basis wall), `tests/test_playbook_spend_chain.py` (9 tests). Orchestrator +
LA + wicket + playbooks regression: **231 passed, exit 0**.

## The chain, and the three things kept separate

> Evidence admits consideration; Standing authorizes; LA spends.

- **Evidence coherence** — `WicketClient.check_playbook_admission` (Slice 3), now reachable from
  the orchestrator via `run(..., playbook_evidence=...)`. Necessary, refuses before Standing.
- **Standing authority** — the unchanged `check()` delegate. Necessary, and it is *not* the spend.
- **LA consume** — the existing, unchanged `LinearAccountantClient` spend seam. The bounded effect.

The orchestrator change is minimal: when `playbook_evidence` is supplied, step 1 routes through the
two-gate playbook admission; otherwise the chain is byte-identical to before. Everything downstream
(standing-spendability gate, LA request, LA consume, Wall-1 operational fence, recomposition) is
untouched.

## The Slice 4 laundering wall — certification is not a spend basis

The LA spend's basis is the **authority** receipt (wicket-seam admission, `verdict="pass"`), NEVER
the **evidence** record (`wicket_playbook_evidence`, `verdict="observe"`). Two mechanisms, both pinned:

1. **By construction** — the orchestrator threads `WicketVerdict.receipt_id` (always the pass
   admission) into the LA request. The observe evidence record is a *side* receipt; it is never on
   the `WicketVerdict`, so it cannot reach LA through the chain.
2. **Defense-in-depth** — `build_authority_admission_verifier(sink)` is the LA `admission_verifier`
   for a playbook spend: a cited admission id is a valid spend basis IFF it resolves to a wicket-seam
   pass admission. Both the pass admission and the observe record resolve in the store, so
   "does it resolve?" is *not* enough — `is_authority_admission_receipt` checks gate+verdict.
   `test_la_refuses_evidence_record_cited_as_spend_basis` manually cites the observe id as the LA
   basis and LA refuses (`dangling_receipt_reference`, request callable never invoked): certification
   could not reserve capacity.

## Failure taxonomy (operator's table — all pinned, by owner)

| Failure                                  | Owner / seam                                    | Test |
|------------------------------------------|-------------------------------------------------|------|
| tampered evidence / bad closure          | evidence gate · `SEAM_WICKET` / `playbook_evidence_unbound` | `test_tampered_evidence_refuses_before_standing` |
| no Standing grant                        | authority gate · `SEAM_WICKET` / `standing_required` | `test_missing_standing_refuses_before_la` |
| LA denied / unavailable                  | effect gate · `SEAM_LA_REQUEST` / `capacity_refused` | `test_la_denied_surfaces_at_la_seam_not_wicket` |
| certification cited as spend basis       | authority-admission wall · LA `dangling_receipt_reference` | `test_la_refuses_evidence_record_cited_as_spend_basis` |
| observe record promoted to authority     | refused by `is_authority_admission_receipt`     | `test_authority_predicate_rejects_observe_record` |

Plus: success consumes (`test_evidence_authority_spend_consumes`); the spend basis is the pass
admission not the observe record (`test_spend_basis_is_authority_not_evidence`); non-playbook callers
are unchanged (`TestNonPlaybookCallersPreserved`).

## Did Slice 4 force Track A pickup? — NO (and that is the finding)

**It did not.** The minimal playbook-governed spend was expressible entirely through existing
interfaces — `WicketClient.check_playbook_admission`, `StandingClient`, `LinearAccountantClient`,
`CookedContextOrchestrator` — with **zero edits to `supervisor.py`, `activation.py`, or any executor**.
The orchestrator already threads authority→spend; the LA seam already *is* the spend boundary at
harness grade. So the boss fight the operator named —

> Perfect playbook evidence and valid Wicket admission still cannot consume capacity unless LA
> receives the proper *authority-bound* spend request

— is satisfied here, by the authority-admission wall, without reaching Track A.

**Why the existing path was sufficient, precisely:** Slice 4's goal is to prove the composition
*shape* (evidence → authority → spend without collapsing a layer). That shape is fully expressible
against the LA stub's injected callables and the orchestrator's existing receipt-threading. Nothing
in proving the shape requires durable, cross-process, exactly-once custody.

**Where Track A genuinely becomes forced (named, NOT built):** the *runtime/durable* boundary, not
the shape. Two concrete obstructions a later slice will hit that this one did not:

1. **Durable exactly-once spend.** The LA stub's `AlreadyConsumed` replay-kill runs against
   in-memory injected callables. A real playbook spend that must be exactly-once against **durable
   custody** is precisely `activation.py`'s four-office transaction (admissibility · act-standing ·
   exactly-once spend · durable custody). That is the minimal Track A pickup for *persisted* spend.
2. **Live tool-dispatch wiring.** Proving the shape is not the same as routing a **supervised
   agent's actual tool call** (the `supervisor.py:752/:433` pre-tool gate) through this
   evidence→authority→spend chain via the Standing grant-use path. That wiring is the supervisor
   hot-path pickup — and it should be opened by a slice whose goal is *runtime enforcement*, with a
   forcing case that says exactly which agent dispatch is blocked, not by tool-tourism.

So: Slice 4 is the **shape** specimen and it lands clean. Track A's forcing case is the **durable
runtime** specimen — adjacent, inevitable, and still correctly deferred until a slice actually needs
persisted/enforced spend. Reaching into the supervisor here to "prove spend" would have been
tool-tourism; the harness already proves the shape.

## Intentionally NOT done (stop line held)

- No `supervisor.py` / `activation.py` / executor edits. No durable spend ledger.
- No Standing semantics change. No new LA refusal vocabulary (the wall reuses
  `dangling_receipt_reference`: there is no *admission* at an evidence-record id).
- No generalized executor wiring, no broad playbook runtime, no registry/remote/scheduling.

## Next possible slice (do NOT start without operator go)

Slice 5 candidate — **durable / enforced playbook spend**: route a persisted, exactly-once
playbook spend through `activation.py`'s transaction (Track A), and/or wire a supervised agent's
tool dispatch through this chain (`supervisor.py`). This is the slice that *does* force the
transition-kernel pickup, with the forcing case the runtime obstruction supplies.
