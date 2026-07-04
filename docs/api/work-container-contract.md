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
work that can move across provider boundaries — Hermes, Porter, Polytoken, NQ,
Antigravity — without losing custody or letting the transit system pretend to be
the cargo. (Maude is not in this list: it is an operator/ingress *consumer*, not a
dispatch target — see provider-integration.md §1.)

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

**No law-bearing field is invented.** Every field that carries scope, ration,
admission, or custody projects an existing, shipped AG artifact (below),
serialized at the bonded origin (AG) and sealed by digest. The few fields that do
*not* project a shipped instance carry no authority: `work_id` (a fresh id),
`capability_requirements` (a *requirement* expressed in the existing
`chain_gate.CapabilityClass` vocabulary), and `schema_version` (metadata).

| WorkContainer element              | Projected from (shipped)                                        |
| ---------------------------------- | --------------------------------------------------------------- |
| `admission_ref`                    | `gate_receipt.GateReceipt` (the AG admission/dispatch decision)  |
| `origin.proposal_ref`              | `plan_review.Proposal` (content hash)                           |
| `origin.playbook_ref`              | `playbooks` `PlaybookSpec`/`QueuedPlaybook` digest              |
| `scope_projection` (+ `source_ref`)| `playbooks.RationCard` (`ration_card.py`) — read-only snapshot   |
| `ration_projection` (+ `source_ref`)| `playbooks.RationCard` locked axes — read-only snapshot          |
| `acceptance` / `stop_conditions`   | `plan-envelope-v0` acceptance_criteria / stop_conditions        |
| `receipt_expectations`             | `gate_receipt.GateReceipt`, `ReviewPacket`                      |
| `custody.digest` (seal)            | `gate_receipt.canonical_json` + sha256 discipline               |

The WorkContainer is the **single serialized wire record** that binds these — it
does **not** re-implement any of them, and it is **not** a new law-bearing kernel
object. AG internals stay `CertifiedPlaybook` / `RationCard` / `ReviewPacket` /
`GovernedPlanBinding`; the WorkContainer is their *exported* projection.

### 3.1 A valid container is NOT admission

Schema validity and custody are **never** sufficient to invoke or rely. A
WorkContainer carries `admission_ref` — a citation to the AG gate receipt that
admitted the work — and **reliance requires re-verifying that receipt**, not
trusting the container. Possession of a well-formed container proves only that
someone serialized one.

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

A provider reports what *it* did (its lifecycle). AG decides whether that
testimony is admissible by emitting a **`gate_receipt`** — verdict ∈
{`pass`, `warn`, `block`, `observe`, `proceed`}, role `authority` for a grant
(`gate_receipt.py`, `plan_review.authorize_agenda`). **There is no separate
AG-outcome enum; the existing verdict vocabulary is the outcome.** The adapter
maps provider testimony into review *input*, never aliases it to a verdict:

```
provider.completed_observed   →  AG review  →  gate_receipt(verdict ∈ pass|warn|block|observe|proceed)
provider status               =  INPUT to that review, never a substitute for it
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
  work_id                     # fresh id (envelope metadata, not a projected field)
  admission_ref               # REQUIRED: the AG gate_receipt that admitted this work — a citation to RE-VERIFY, not to trust
  origin:        { proposal_ref?, playbook_ref?, submitted_by, standing_basis_ref? }
  intent                      # one-sentence outcome (from plan-envelope goal)
  capability_requirements[]   # CapabilityClass values the provider must support (a requirement, not a projection)
  scope_projection:   { source_ref, allowed_read_paths[], allowed_write_paths[], forbidden_paths[] }
                              # read-only snapshot of the cited RationCard; a provider may only FURTHER RESTRICT
  ration_projection:  { source_ref, network, external_send, git, doctrine_writes, observe_only,
                        max_wallclock_seconds?, max_artifact_bytes? }   # read-only snapshot of the cited RationCard
  acceptance:    { required_checks[], required_artifacts[] }
  stop_conditions[]
  receipt_expectations:  { run_receipt: true, obstruction_on_block: true }
  custody:       { digest, parent_container_ref?, decomposition_lineage[] }
```

`scope_projection` / `ration_projection` are **read-only snapshots** of a
RationCard (each carries the `source_ref` digest it projects). They are **not a
grant**: a provider may only *further restrict* them, and AG dispatch
(`governed_dispatch`) — never the container — is the enforcement source. Naming
them `*_projection` is deliberate: the raw booleans/paths are a temptation to
enforce-as-permission, and the contract forbids that reading.

Serialization discipline (reuse, do not re-derive): canonical JSON (sorted keys,
compact separators, ASCII-safe) per `gate_receipt.canonical_json`;
`sha256:<64hex>` for every digest/ref field; top-level `schema_version`.

## 7. What a reviewer must be able to confirm (the real gate)

- **No law-bearing field is invented** (§3): every scope/ration/admission/custody
  field projects a shipped AG object; the non-projected fields (`work_id`,
  `capability_requirements`, `schema_version`) carry no authority.
- **A valid container is never admission** (§3.1): `admission_ref` cites a
  re-verifiable AG gate receipt; validity/custody is not reliance.
- The container **grants no permission** and **mints no standing** — it carries a
  read-only `*_projection` of a RationCard (with `source_ref`); a provider may
  only further restrict it, and AG dispatch is the enforcement source.
- No parallel verdict enum (§4); the AG-review outcome is an existing
  `gate_receipt` verdict, not a new word set (§4.1).

## 8. Not in this slice (gated follow-ons)

- No `ProviderRegistry` / `ProviderDescriptor` Python (Slice 2, gated on this
  contract being reviewed).
- No live `governed_dispatch` emission/consumption of a serialized WorkContainer
  (Slice 4, **gated on CD-4** proving the runtime shape).
- No Antigravity adapter (Slice 5 — a test case, never the interface designer).
