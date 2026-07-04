# Provider Integration Contract (v1)

**Status: DRAFT / CANDIDATE.** Non-binding until ratified *and* a first conforming
provider exists. **No provider is declared conforming by this document.**

> This contract exports AG's existing admission and rationing machinery to agents
> and providers. It is not a replacement authority layer. Agents may propose;
> providers may perform or testify; only AG admits reliance.

> **This slice exports names for existing law; it does not create a new authority
> surface.**

This is a projection of the shared law in
[`work-container-contract.md`](work-container-contract.md) onto the **AG →
provider** direction. Read that document first.

A *provider* is an external system that **performs, transforms, transports, or
witnesses** work — Maude, Hermes, Porter, Polytoken, NQ, Antigravity. Contrast an
*agent* (`agent-integration.md`), which *asks and proposes*.

---

## 1. Provider kinds (capability-shaped, not harness-shaped)

Do not force everything into "harness." A provider declares a **kind** so its
capabilities are named honestly (this is why Polytoken gets a transform lane
instead of a fake execution one):

| provider_kind          | Examples                        | Primary verb        |
| ---------------------- | ------------------------------- | ------------------- |
| `execution_harness`    | Maude, Hermes, Antigravity CLI  | run                 |
| `agent_runtime`        | Claude Code, Codex, Antigravity | run (agentic)       |
| `transform_provider`   | Polytoken                       | transform           |
| `substrate_courier`    | Porter                          | transport           |
| `external_witness`     | NQ                              | witness             |
| `communication_adapter`| email now; Slack/webhook later  | send (scoped)       |
| `artifact_store`       | blob / corpus / cache           | store / retrieve    |

Descriptor shape is normative in
[`../../schemas/provider_descriptor.v1.json`](../../schemas/provider_descriptor.v1.json)
(DRAFT). It projects `AdapterCapabilities` (`runtime/adapter.py`) + a
`CapabilityClass` set (`chain_gate.py`) and carries `authority_claims: []` —
**empty unless the provider literally is an AG component.**

## 2. Provider verbs

```
describe()                     # return the provider_descriptor
can_accept(work_container)     # not_supported | available | held  (pre-flight, no side effects)
prepare(work_container)
run | transform | witness | transport (work_container, ration)
status(run_id)
cancel(run_id)
artifacts(run_id)
receipt(run_id)                # a provider_run_receipt (testimony)
obstruction(run_id)            # a provider_obstruction when blocked
```

`can_accept` mirrors the existing membrane: it is the provider-side analogue of
`governed_dispatch.PreflightDecision` (`allow | would_block | blocked`). AG remains
the decider; `can_accept` only reports capability, never authority.

## 3. Provider status is NOT an AG verdict (the load-bearing rule)

A provider reports what *it* did; AG decides whether that testimony is admissible.
Canonical provider states (see
[`../../schemas/provider_run_receipt.v1.json`](../../schemas/provider_run_receipt.v1.json)):
`not_supported` · `available` · `held` · `running` · `completed_observed` ·
`completed_inadmissible` · `blocked` · `refused` · `cancelled` · `timed_out`.

The adapter **maps**, it does not alias:

```
provider.completed_observed   →  AG review  →  admitted | held | refused | inadmissible
provider.blocked              ≠  AG.refused
provider.success              ≠  reliance
```

Less churchy:

```
Maude success       ≠ admitted success
Hermes capability   ≠ standing
Polytoken transform ≠ semantic preservation
Porter receipt      ≠ policy permission
NQ witness          ≠ authorization
Antigravity plan    ≠ approved plan
```

This is exactly the constellation-adapter idiom already shipped: injected
callable, pre-call AG-side refusal, closed refusal vocabulary, receipt linkage by
parent id (`standing_client.py`, `wicket_client.py`,
`linear_accountant_client.py`, `nightshift_adapter.py`). A provider adapter is a
witness/courier/tool with receipts — never a source of authority.

## 4. Where AG decision becomes provider invocation

The membrane is `governed_dispatch.py`: `PreflightRequest → PreflightDecision →
DispatchContext → DispatchResult`. A provider is invoked **only** on an `allow`
decision; its `DispatchResult` is recorded as testimony and reviewed. The existing
`RuntimeAdapter` protocol (`runtime/adapter.py`, with `AdapterCapabilities`) is the
concrete execution-provider interface today; whether it generalizes to all
provider kinds or needs a thin `ProviderAdapter` super-protocol is the open
question posed in `agent-integration.md` §6 — to be answered by review, not
pre-empted by code here.

## 5. Receipts and obstructions (testimony, not authority)

- A **provider_run_receipt** is what a provider returns after performing:
  execution outcome + digests + declared artifacts. It reuses the receipt_v1
  decision/execution vocabulary and the `gate_receipt` verdict/role/unsettled
  vocabulary — no parallel enums. It is testimony; AG's own gate receipt is the
  authority.
- A **provider_obstruction** is what a provider returns when it cannot proceed:
  the blocked step, the refusal verbatim, and what must change upstream
  (`plan-envelope-v0` §5 reserved this shape). An obstruction is honest reporting,
  never a downgrade path.

## 6. Pass / fail criteria for any future provider work

**PASS:** reuses `RuntimeAdapter` / `governed_dispatch`; treats the WorkContainer
as a projection; keeps Maude as *one* provider (not the privileged spine); gives
Polytoken a transform lane; treats Antigravity as a *test case*; adds conformance
tests before any live integration.

**FAIL:** a new HTTP API first; a registry that *implies* provider trust; a
duplicate verdict enum; a WorkContainer that grants permissions; provider
"success" entering receipt/reliance without AG review; Maude becoming the
mandatory gateway for all harnesses; Antigravity-specific permissions leaking into
the generic contract.

## 7. Not in this slice (gated follow-ons)

- No `ProviderRegistry` / `ProviderDescriptor` Python (Slice 2 — gated on this
  contract being reviewed: it must first establish what a descriptor *means*, what
  conformance does/doesn't imply, how provider status is kept from becoming an AG
  verdict, and how a WorkContainer projects the existing machinery).
- No conforming-provider declaration; no Maude/Claude-Code registration (Slice 3).
- No live `governed_dispatch` emission/consumption of a WorkContainer (Slice 4,
  **gated on CD-4**).
- No Antigravity adapter or probe (Slice 5).
