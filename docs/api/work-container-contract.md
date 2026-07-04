# WorkContainer Contract (v1) — the portable ABI

**Status: DRAFT / CANDIDATE.** Non-binding until ratified *and* a first
conforming implementation exists. This document names an export surface over
existing Agent Governor (AG) machinery; it does not change any runtime behavior.

> This contract exports AG's existing admission and rationing machinery to agents
> and providers. It is not a replacement authority layer. Agents may propose;
> providers may perform or testify; only AG admits reliance.

> **This slice exports names for existing law; it does not create a new authority
> surface.**

> This slice is coherent but not complete: it ratifies shared vocabulary and
> candidate schemas across the agent, provider, and WorkContainer surfaces,
> without declaring any provider conforming or changing runtime dispatch.

This is the **deepest** of the three integration documents. `agent-integration.md`
and `provider-integration.md` are projections of the shared law defined here.
Read this one first.

---

## 1. What a WorkContainer is

A **WorkContainer** is a sealed, bounded, serialized unit of *already-admitted*
work that can move across provider boundaries — Maude, Hermes, Porter, Polytoken,
NQ, Antigravity — without losing custody or letting the transit system pretend to
be the cargo.

It is a **bill of lading, not a second Governor wearing a fake mustache.**

> WorkContainer carries admitted work across provider boundaries. It does not
> admit work. It does not grant standing. It does not replace RationCard,
> ReviewPacket, or governed_dispatch.

The primitive is **not** `epic → sprint → task`. It is **bounded transferable
cargo**:

```
proposal / plan-envelope  →  AG admits + rations  →  WorkContainer (sealed)  →  provider performs / testifies  →  AG reviews
```

The full freight framing lives in [`../candidates/WORK_CONTAINER.md`](../candidates/WORK_CONTAINER.md).

## 2. The one law (shared by all three documents)

```
An agent can ask.
A provider can perform (or transform, transport, witness).
Only AG can admit.
Only admitted work can feed reliance.
No artifact, transcript, provider success, or transformed output can supply its
own authority.
```

### 2.1 The killer invariant

> **Decomposition must preserve custody. Recomposition must not create authority.**

This is not aspirational — it is already enforced in code by
`RecompositionReceipt` + `account_boundaries()` (the `refused_laundering` outcome
when an admitted decomposition boundary is unaccounted) and `RecompositionRefusal`
at the recomposition seam, where **recomposition's only verb is refuse**
(`src/governor/pipeline_types.py`, `src/governor/cooked_context_orchestrator.py`).
You can unload, reload, route, split, batch, defer, or inspect cargo — but you
cannot change what was authorized just because it passed through a terminal.

## 3. WorkContainer is a PROJECTION, not a source of truth

Every WorkContainer field is a **projection of an existing, shipped AG artifact**,
serialized at the bonded origin (AG) and sealed by digest. The container invents
nothing:

| WorkContainer element        | Projected from (shipped)                                   |
| ---------------------------- | ---------------------------------------------------------- |
| `origin.proposal_ref`        | `plan_review.Proposal` (content hash)                      |
| `origin.playbook_ref`        | `playbooks` `PlaybookSpec`/`QueuedPlaybook` digest         |
| `routing` (scope/perms)      | `playbooks.RationCard` (`ration_card.py`) — read-only copy |
| `acceptance` / `stop`        | `plan-envelope-v0` acceptance_criteria / stop_conditions   |
| `receipts` (expectations)    | `gate_receipt.GateReceipt`, `ReviewPacket`                 |
| `custody.digest` (seal)      | `gate_receipt.canonical_json` + sha256 discipline          |

The WorkContainer is the **single serialized wire record** that binds these — it
does **not** re-implement any of them, and it is **not** a new law-bearing kernel
object. AG internals stay `CertifiedPlaybook` / `RationCard` / `ReviewPacket` /
`GovernedPlanBinding`; the WorkContainer is their *exported* projection.

## 4. Shared status vocabulary (reused verbatim — no parallel enums)

The schemas reuse existing AG vocabulary. **Do not invent new verdict/status
enums.**

- **AG verdicts** (`gate_receipt.py`): `pass` · `warn` · `block` · `observe` ·
  `proceed`.
- **Receipt roles** (`gate_receipt.py`): `measurement` · `proposal` · `authority`
  · `recovery_plan` · `reset`. Only `authority` confers force, and only an
  operator emits it (`plan_review.authorize_agenda`).
- **Unsettled kinds** (`gate_receipt.NonDischargeClaim`): `authority` ·
  `evidence_sufficiency` · `freshness` · `scope` · `standing` ·
  `consumer_reliance`.
- **Provider-side decision actions** (`libs/receipt_v1/schema/receipt.schema.json`):
  `allow` · `deny` · `transform` · `escalate`; execution status `success` ·
  `failure` · `timeout` · `skipped`.

### 4.1 Provider status is NOT an AG verdict

A provider reports what *it* did. AG decides whether that testimony is admissible.
The adapter must map, never alias:

```
provider.completed_observed   →  AG review  →  admitted | held | refused | inadmissible
provider.blocked              ≠  AG.refused
provider.success              ≠  reliance
```

This mirrors the constellation-adapter idiom already in the codebase
(`nightshift_adapter.translate_verdict` is a deterministic map, not a decision;
`wicket_client`/`standing_client` mint their own receipts rather than promoting a
downstream verdict).

## 5. Playbook demotion

AG's own playbook support is **vestigial — "no longer the organizing skeleton,"
not "rip out."** Broad playbook usage has been thin; the one identifiable *live*
consumer is the conveyor-dogfood campaign itself (CD-2 ran on the playbook
conveyor; CD-4 is staged on it) — the migration-bridge case, and reason enough
not to break it. Under this contract the playbook becomes **one origin format**,
not the spine:

```
PlaybookSpec / QueuedPlaybook  →  compiles / contributes to  →  WorkContainer  →  dispatched to  →  Provider
```

- Playbook ≠ dispatch law / provider ABI / standing / authority.
- Playbook = curated recipe / origin artifact / compatibility carrier.

Keep playbooks for exactly three things: (1) human-authored repeatable recipes,
(2) fixtures / corpus / regression material, (3) the CD-4 live-run migration
bridge. Do **not** deepen them, delete them in this slice, or let them design this
API.

> Playbooks remain a supported origin and recipe format, but they are not the
> portable integration contract. Provider-facing execution is expressed through
> WorkContainer projections derived from admitted AG machinery. A playbook may
> contribute to a WorkContainer; it does not itself authorize, dispatch, or
> certify provider work.

**Forbidden shapes:** Provider API calling `PlaybookRunner`; Agent API emitting a
`PlaybookSpec`; Maude/Antigravity consuming a Playbook directly.
**Clean shape:** Provider API consumes a WorkContainer; Agent API submits a
Proposal / PlanEnvelope / materials; a Playbook *compiles into* a WorkContainer
when applicable.

## 6. Serialized shape

Normative field definitions live in
[`../../schemas/work_container.v1.json`](../../schemas/work_container.v1.json)
(DRAFT). Illustrative shape (references and digests, not a law dump):

```
work_container.v1
  work_id
  origin:        { proposal_ref?, playbook_ref?, submitted_by, standing_basis_ref? }
  intent         # one-sentence outcome (from plan-envelope goal)
  scope:         { allowed_paths[], forbidden_paths[] }        # projected from RationCard
  ration:        { network, external_send, git, doctrine_writes, observe_only,
                   max_wallclock_seconds?, max_artifact_bytes? }  # projected from RationCard
  capability_requirements[]   # CapabilityClass values the provider must support
  acceptance:    { required_checks[], required_artifacts[] }
  stop_conditions[]
  receipt_expectations:  { run_receipt: true, obstruction_on_block: true }
  custody:       { digest, parent_container_ref?, decomposition_lineage[] }
```

Serialization discipline (reuse, do not re-derive): canonical JSON (sorted keys,
compact separators, ASCII-safe) per `gate_receipt.canonical_json`;
`sha256:<64hex>` for every digest/ref field; top-level `schema_version`.

## 7. What a reviewer must be able to confirm (the real gate)

- Every field traces to a shipped AG object (§3) — no invented authority fields.
- The container **grants no permission** and **mints no standing** — it *carries*
  a RationCard projection; it does not become one.
- No parallel verdict enum (§4).
- The status≠verdict mapping (§4.1) is present and one-directional.

## 8. Not in this slice (gated follow-ons)

- No `ProviderRegistry` / `ProviderDescriptor` Python (Slice 2, gated on this
  contract being reviewed).
- No live `governed_dispatch` emission/consumption of a serialized WorkContainer
  (Slice 4, **gated on CD-4** proving the runtime shape).
- No Antigravity adapter (Slice 5 — a test case, never the interface designer).
