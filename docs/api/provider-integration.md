# Provider Integration Contract (v1)

**Status: v1 — RATIFIED 2026-07-05 (operator, Option A per docs/campaigns/public-mvp/ratification-memo-work-container-v1.md). First provider: claude_code, STRUCTURALLY conformant (registered, fail-closed) with live supervised evidence via CD-4B (sess_aabb2a056f9f); RUNTIME (container-consumption) conformance not yet demonstrated — gated on S4 dispatch wiring. Schema changes from here are versioned (v1 → v2), not silent.** Superseded preamble (historical): non-binding until ratified *and* a first conforming
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
witnesses** work — Claude Code, Hermes, Porter, Polytoken, NQ, Antigravity.
Contrast an *agent* (`agent-integration.md`), which *asks and proposes*, and an
*operator/ingress consumer* (e.g. Maude), which submits plans and reads decisions
but is never a dispatch target (§1).

---

## 1. Provider kinds (capability-shaped, not harness-shaped)

Do not force everything into "harness." A provider declares a **kind** so its
capabilities are named honestly (this is why Polytoken gets a transform lane
instead of a fake execution one):

| provider_kind          | Examples                        | Primary verb        |
| ---------------------- | ------------------------------- | ------------------- |
| `execution_harness`    | Hermes, Antigravity CLI         | run                 |
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
**always empty: a provider descriptor never declares authority.** (An external
provider is never an AG component; AG's own components are not described by this
schema. The schema enforces this with `maxItems: 0`.)

### 1.1 Maude is NOT a provider (deliberate non-example)

A provider is something AG can dispatch a WorkContainer *toward* and later receive
testimony *from*. The **Maude** operator surface does not fit that: it is an
operator/ingress **consumer** — it submits plans and reads AG decisions /
supervised-run state, but AG does not send it WorkContainers. It talks to the
clerk; it is not a bailiff. Modeling the operator desk as a provider now would be a
category error that teaches later integrations the wrong shape. If Maude later
exposes a *provider-facing execution service* (e.g. `maude-supervisor-provider`),
**that service** may register as its own descriptor — but the operator surface
itself is not a provider. The first honest provider descriptor is Claude Code
(`agent_runtime`, `src/governor/provider_descriptors.py`).

## 2. Provider verbs

```
describe()                     # return the provider_descriptor
can_accept(work_container)     # not_supported | available  (capability pre-flight, no side effects)
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

A provider reports what *it* did — its **observable lifecycle**, never a judgment
about its own admissibility. The canonical provider states (see
[`../../schemas/provider_run_receipt.v1.json`](../../schemas/provider_run_receipt.v1.json))
are lifecycle only: `not_supported` · `available` · `running` ·
`completed_observed` · `blocked` · `cancelled` · `timed_out`. A provider **never**
reports `refused`/`held`/`inadmissible` — those are AG verdicts, not provider
states; a provider that cannot proceed is `blocked` and emits a
`provider_obstruction`.

AG decides admissibility by emitting a **`gate_receipt`** (verdict ∈ `pass` ·
`warn` · `block` · `observe` · `proceed`, role `authority` for a grant). Provider
lifecycle is **input** to that review, never a substitute for it — there is no
separate AG-outcome enum:

```
provider.completed_observed   →  AG review  →  gate_receipt(verdict ∈ pass|warn|block|observe|proceed)
provider status               =  INPUT to that review, never a substitute
provider.success              ≠  reliance
```

Less churchy:

```
Claude Code success ≠ admitted success
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

## 6. What conformance means (and does not)

*Normative — this section closes the gate on any future ProviderRegistry
(Slice 2). A registry may not admit a provider until conformance is defined, and
this is that definition.*

A provider is **conformant** to this contract iff it does ALL of:

1. **Speaks the shapes.** Accepts a `work_container.v1` and returns
   `provider_run_receipt.v1` / `provider_obstruction.v1` valid against the DRAFT
   schemas.
2. **Reports lifecycle, not verdicts.** Its `provider_status` is drawn only from
   the lifecycle set (§3); it never emits `refused`/`held`/`inadmissible`, and
   `ag_review` is always null.
3. **Only further restricts.** It treats `scope_projection` / `ration_projection`
   as read-only snapshots it may tighten but never widen or treat as a grant;
   enforcement stays with AG dispatch + the outer cage.
4. **Reports obstruction honestly.** On any block it emits a `provider_obstruction`
   with a closed `refusal_class` and the refusal verbatim.
5. **Declares no authority.** Its `provider_descriptor` carries `authority_claims: []`.

Conformance means ONLY the above. It explicitly does **NOT** imply:

- **Trust** — a conformant provider is a well-behaved witness/courier/tool; it is
  not trusted to admit, authorize, or rely.
- **Admission of its output** — AG still reviews every run; conformance is about
  the *shape* of testimony, not its *acceptance*.
- **Standing** — conformance is not identity or standing (verified separately,
  `standing_client`).

**Resolved in Slice 2** (`src/governor/provider_registry.py`): a descriptor is a
*declaration*, so registration verifies only STRUCTURAL conformance (fail-closed
on any authority claim) and confers no trust; RUNTIME conformance needs live
evidence (Slice 3+). Revocation drops routing eligibility (the entry is kept for
audit); freshness is by descriptor `version` (a version change is a new
descriptor that must be re-registered). A registry entry is **routing eligibility
only** — the registry has no admit/authorize/trust/grant method. Still deferred
to Slice 3 (needs a live provider): the runtime-conformance **test suite**.

## 7. Pass / fail criteria for any future provider work

**PASS:** reuses `RuntimeAdapter` / `governed_dispatch`; treats the WorkContainer
as a projection; keeps **no single provider as the privileged spine** (Claude Code
is one provider among future many; Maude is a consumer, not a provider); gives
Polytoken a transform lane; treats Antigravity as a *test case*; adds conformance
tests before any live integration.

**FAIL:** a new HTTP API first; a registry that *implies* provider trust; a
duplicate verdict enum; a WorkContainer that grants permissions; provider
"success" entering receipt/reliance without AG review; **any one surface (e.g.
Maude) becoming the mandatory gateway** for all harnesses; Antigravity-specific
permissions leaking into the generic contract.

## 8. Build-vector status

- Slice 1 (this contract) — landed + adversarially reviewed + hardened.
- **Slice 2** `ProviderRegistry` primitive — landed (`src/governor/provider_registry.py`).
- **Slice 3** first structural descriptor — landed: Claude Code (`agent_runtime`),
  `runtime_capabilities` projected live from `ClaudeCodeAdapter`, STRUCTURAL only
  (`src/governor/provider_descriptors.py`). Maude deliberately excluded (§1.1).
- **Slice 4 ✓ / 4b ✓** — WorkContainer projection (`work_container.py`) + the
  admission emit/consume bridge (`work_container_bridge.py`): admission is a real,
  resolvable `gate_receipt`, consumption re-verifies the container against it.
- **Slice 5 / AGY-0 ✓** — Antigravity capability **probe**
  (`runtime/adapters/antigravity_probe.py`) + a STRUCTURAL `antigravity_cli`
  descriptor (thinner than Claude Code — no live adapter, so no projected
  `runtime_capabilities`). Recognition, not admission: the probe emits
  compatibility evidence (`evidence_kind = "probe_compatibility"`, never live
  testimony) and agent mode is blocked in this environment. Antigravity is the
  *test case*, not the interface designer. Spike doc:
  `docs/playbooks/antigravity-adapter-spike.md`.
- Still gated: **AGY-1** (sandboxed one-shot Antigravity runner behind the outer
  cage) and the live runtime-conformance suite it would exercise.
