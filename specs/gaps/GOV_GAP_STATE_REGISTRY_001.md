# GOV_GAP_STATE_REGISTRY_001 — State Index / Projection Registry

**Status:** SCOPE (candidate). Slice 0 authorized (export-only). Everything below Slice 0 is
recorded, not ratified.
**Filed:** 2026-07-01
**Branch of discovery:** `feat/playbooks-synthetic-conveyor` (playbooks/governed-build-loop forcing function)
**Landmine (keep it visible):**

> **Registry makes state legible; it does not make state true.**
> SQLite may remember what AG thinks it saw. It does not decide what AG is allowed to do.

This is a scoping doc, not an implementation plan for the whole thing. It names the surface
early (per YAGNI §"name early, ratify lazily") and authorizes exactly one small slice.

---

## Forcing case (why this is not YAGNI-fenced)

AG has accumulated a large prose-shaped planning/state corpus — gaps, playbooks, exit tickets,
review packets, campaign capsules, handoff notes, parked candidates. This was correct while the
system was exploratory. It is now **too lossy for governed build loops**: the playbooks want
machine-readable answers to *"what is ready / what is next / what is blocked / what depends on
what"* and today those answers live in prose that drifts.

The forcing function is concrete and current: `docs/playbooks/` (governed-playbooks, build-phases,
next-gate-selection-review) plus the synthetic-conveyor track want queryable state, review gates,
receipts, dependency closure, and allowed transitions. The operator has explicitly ruled this **in
scope, not speculative**: "This is not fenced by YAGNI. We do, in fact, need it. Badly."

**The catch that keeps YAGNI's teeth:** we authorize a *legibility* slice (export), not an
*authority* slice. Nothing below promotes prose into standing.

---

## What already exists (Codex's report corrected)

Codex's inventory was right about the prose corpus but **missed that AG already hand-maintains a
typed state layer**. This changes the shape of the work from "greenfield registry" to
"reconcile + derive."

### Prose corpus (source of rationale/spec — stays canonical)
- `specs/gaps/*.md` — **111 files.** Gap corpus. Kinds: gap, planned slice, dependency edge,
  promotion candidate, backlog item. E.g. `GAP_BUILD_ORDER.md`,
  `GOV_GAP_STATE_REENTRY_PROTOCOL_001.md`, `GOV_GAP_GOAL_PROMOTION_001.md`.
- `docs/playbooks/*.md` — **25 files.** Playbooks + review gates + exit tickets. E.g.
  `governed-playbooks.md`, `build-phases.md`, `next-gate-selection-review.md`,
  `slice-0..7-exit-ticket.md`, `h2-live-run-contract-review.md`,
  `synthetic-conveyor-s7-contract.md`.
- `docs/campaigns/{ag-admit-self-build,transition-kernel-pickup,governed-playbooks-track-b}/` —
  active campaign capsules. Each has `CAMPAIGN.md`, `STATUS.md`, `NEXT.md`, `DECISIONS.md`, plus
  campaign-specific (`GRANTS.yaml`, `REPLAY.md`, `INVENTORY.md`, `TRANSPORT.md`).
- `working/*.md` — **94 files.** Handoffs, parked candidates, exits, audit notes. E.g.
  `P4_PARKED_2026-06-16.md`, `EXIT_2026-06-23_ag-admit-slice3-needs-human.md`,
  `RESUME_2026-06-15_p4-HIGH-prep.md`.
- `docs/doctrine/decisions/*` + `_validations/*.json` — doctrine + operator decisions + validation
  attestations. (Authority-bearing — see boundaries; the registry *references*, never absorbs.)

### Typed state that ALREADY EXISTS (the reconciliation target)
- **`.governor/backlog/*.json` — 30 hand-authored items.** Schema already present:
  ```json
  { "id", "repo", "kind", "spec_ref", "forcing_case",
    "priority_tier", "status", "acceptance", "note" }
  ```
  Note `repo` is already a field — the multi-source instinct is half-built. Statuses seen in the
  wild include `filed`. `kind` includes `build_slice`.
- **`.governor/campaigns/*.yaml` — schema `ag-campaign-manifest/v0`.** A rich discovery manifest:
  `capsule_dir`, `files{}`, `ratified_decisions[]`, `committed[]`, `state{}`, `next_build{}`,
  `source_code{}`. Explicitly self-labeled *"Inert discovery manifest — NOT live WIP state."*
- `.governor/{decisions,evidence,facts,gate_receipts,instrument}/` — authority-bearing substrates.
  **Out of scope. Do not merge into the state index.**

### Structured precedents in code (design reference only — do not vendor into)
`src/governor/ledgers*.py`, `evidence_store.py`, `promotion_evidence_store.py`,
`libs/receipt_kernel/store_sqlite.py`, `libs/receipt_v1/store.py`.

**Consequence for the design:** the hand-authored `.governor/backlog/*.json` is *both* prior art
(a working schema to steal) *and* a divergence risk (it drifts from the prose it summarizes). Slice
0's export should **cross-check** the prose against the existing JSON and emit warnings on
divergence — not silently overwrite it.

This reframes the whole gap. The question is **not** "should AG get a state registry?" It is:
**AG already has proto-registry fragments; do we consolidate them into a governed projection model
before they fossilize into five incompatible truths?** Machine-readable state already crossed the
membrane. `.governor/` is already not just cache. Hand-authored JSON may already be
quasi-authoritative *by habit*. Migration therefore needs **custody language, not invention
language.**

---

## Three state classes (the provenance/custody axis — do not skip this)

State does not have one origin. Tag every record with a `provenance_class`. This axis is
**orthogonal** to the two lifecycle planes below (an item has one provenance class *and* a
project-lifecycle status *and*, eventually, an execution status).

```text
declared_state    -- operator/agent asserted directly into .governor/
                     (.governor/backlog/*.json, .governor/campaigns/*.yaml).
                     NOT derived. Authoritative about *intent*, not about *facts*.
observed_state    -- scanner output derived from prose/docs/specs.
                     Testimony about what the prose says. Disposable, re-derivable.
execution_state   -- governor-admitted / queued / running / consumed lifecycle.
                     Written ONLY by governed admission mechanisms. == plane 2.
```

### The ugly fork: is `.governor/backlog/*.json` source or cache?

Don't let this slide by as "existing files." It is the custody decision the whole migration turns
on, and the two answers pull opposite ways:

- **If source** → the scanner must never overwrite it; on divergence, the *prose* is the suspect
  (stale doc), and the JSON carries operator intent that outranks a summary.
- **If cache** → it is regenerable, prose is canonical, and the JSON is a stale projection to be
  rebuilt.

**Ruling for this spec:** `.governor/backlog/*.json` is **declared_state — operator-declared, not
derived, authoritative about intent but not about facts, and below receipt custody.** Practical
consequences:

1. It is a **first-class scanner input**, tagged `provenance_class: declared`. Never re-derived,
   never overwritten by Slice 0.
2. It is **not authority.** "An operator typed it into `.governor/`" is standing to *intend*, not
   proof that the work is done, ready, or admitted. It cannot mint execution_state.
3. Divergence between a `declared` item and its cited `spec_ref` prose (`observed`) is surfaced as a
   warning **with direction unattested** — the export does not adjudicate which side is stale. It
   reports the disagreement; a human or a governed step resolves it.
4. Because it is declared (not cached) it earns a provenance tag that a reader can never confuse with
   scanner output or with a gate verdict. That tag *is* the custody language the migration needs.

This keeps boundary #1 intact: declared ≠ observed ≠ execution, and none of the three is authority.

---

## State-kind taxonomy (closed-ish vocabulary)

Every scanned artifact classifies to exactly one `kind`; ambiguous → `other` + warning.

| kind | seen in |
|------|---------|
| `gap` | `specs/gaps/*.md` |
| `planned_slice` | gap sub-slices, `docs/playbooks/slice-*`, campaign `NEXT.md` |
| `playbook` | `docs/playbooks/{governed-playbooks,build-phases,...}.md` |
| `review_gate` | `docs/playbooks/*-review.md`, `*-exit-ticket.md`, `*-contract.md` |
| `receipt_ref` | pointers into `.governor/gate_receipts/`, `_validations/` (ref only) |
| `doctrine_note` | `docs/doctrine/**` |
| `backlog_item` | `.governor/backlog/*.json` |
| `parked_candidate` | `working/*PARKED*`, `working/candidate-*` |
| `promotion_candidate` | gaps/working marked promotion-pending |
| `work_packet` | active campaign capsule, `working/RESUME_*`, `working/EXIT_*` |
| `dependency_edge` | "blocked on", "depends on", "supersedes" relations in prose |
| `waiver` / `exception` | `GRANTS.yaml`, `docs/doctrine` exception classes |
| `operator_decision` | `DECISIONS.md`, `docs/doctrine/decisions/*` |
| `other` | ambiguous — fallback, always warns |

Project-lifecycle status vocabulary (v0): `discovered`, `triaged`, `planned`, `active`, `blocked`,
`parked`, `ready_for_review`, `reviewed`, `closed`, `superseded`, `rejected`.

---

## The two-plane split (preserve from schema v0, even if plane 2 is empty)

A single item answers two different questions. Do **not** collapse them into one status column.

```
project_lifecycle          governor_execution_lifecycle
-----------------          ----------------------------
discovered                 admitted
triaged                    queued
planned                    running
active                     waiting_review
blocked                    denied
parked                     completed
ready_for_review           failed
reviewed                   consumed
closed
superseded
rejected
```

**Hard line:** `planned` ≠ `admitted`. `ready_for_review` ≠ `queued`. `closed` ≠ `consumed`.
Plane 1 (project tracking) is what the export produces. Plane 2 (governor execution) is populated
only through existing governed admission mechanisms (wicket / standing / grants / run receipts) —
the registry *records* it, never *confers* it. Slice 0 produces plane 1 only; plane 2 columns
exist in the eventual schema but stay empty until a governed admission writes them.

---

## Source planes (multi-repo, from day zero)

`.governor/state.sqlite` cannot become "the registry of truth" once sibling repos participate. It is
a **local projection over declared foreign state** — git index + reflog, not the working tree.

Carry `source_namespace` from the first schema even while it only holds `ag`. Foreign state is
**testimony-shaped input, not AG-owned state**: AG indexes Continuity/Spine/NQ **exports**, not
their guts. Every imported row needs provenance (`source_namespace`, `source_export_id`,
`source_commit`, `source_schema`, `source_path`, `source_hash`, `observed_at`, `imported_at`) and a
freshness verdict:

- `fresh` — source fingerprint still matches import
- `stale` — source moved; cached projection may be outdated
- `orphaned` — source/export no longer resolvable

Long-term shape (NOT slice 0):
```
continuity/.governor/exports/state_index_export.v0.json   # each repo owns its export
spine/.governor/exports/state_index_export.v0.json
agent_gov/.governor/state.sqlite                          # AG imports exports, not guts
```

**Invariant:** AG may act on AG-owned state; AG may only *reference* foreign state unless a governed
import/consumption rule explicitly allows more. (Ties to the constellation doctrine: `AG may index
Continuity/Spine state; AG may not absorb Continuity/Spine authority.`)

---

## Hard boundaries (the fence that keeps this honest)

1. **Registry entry ≠ proof.**
2. **Registry status ≠ authority.**
3. **Registry transition ≠ doctrine discharge.**
4. **Registry receipt reference ≠ receipt validity.** A `receipt_ref` row is a pointer; validity is
   still decided by the receipt kernel / gate that owns it.
5. **Docs remain canonical for rationale/spec/prose.** The index summarizes; it does not replace.
6. **Promoted authority still comes only through existing governed mechanisms** (wicket, standing,
   grants, gate receipts). The registry never mints.
7. **`.governor/` is local operational memory, not repo doctrine.** Disposable/rebuildable. If the
   SQLite is deleted, re-running the scanner reconstructs it. It is a cache, not a source.
8. **Do not merge authority-bearing substrates** (`.governor/{decisions,evidence,gate_receipts}`,
   `_validations/`) into the index. Reference them; never absorb them.

### Dangerous overreach to flag and refuse
- Auto-promoting doctrine from scanned docs.
- Treating `STATUS.md` / `NEXT.md` as authoritative *because* scanned.
- Letting a playbook skip a gate because "registry says ready."
- Replacing the receipt/evidence ledgers.
- Building a workflow engine because the word "registry" was said. (See the existing
  `.governor/backlog/loop-as-governed-workflow.json` note: *"Building a workflow engine instead of
  running the loop is the quarry calling again."* — the same trap applies here.)

---

## Slice 0 (AUTHORIZED): `state_index_export.v0`

Export, not registry. A deterministic read-only scanner that says *"here is what the current
prose-shaped state appears to contain"* — nothing more.

### What it does
Scan and emit deterministic JSON records:
- `specs/gaps/*.md`
- `docs/playbooks/*.md`
- `docs/campaigns/*/{CAMPAIGN,STATUS,NEXT,DECISIONS,INVENTORY,TRANSPORT}.md`
- `docs/campaigns/*/GRANTS.yaml`
- `working/*.md`
- `.governor/backlog/*.json` **(reconciliation input — cross-check, do not overwrite)**

### Record shape
```json
{
  "schema": "state_index_export.v0",
  "source_namespace": "ag",
  "provenance_class": "declared | observed",
  "id": "<stable, path-derived or front-matter id>",
  "kind": "<taxonomy above; ambiguous -> 'other'>",
  "status": "<project_lifecycle value; unknown -> null + warning>",
  "title": "<first heading / front-matter title>",
  "source_path": "<repo-relative>",
  "source_hash": "<sha256 of file bytes>",
  "warnings": ["<code: message>", ...]
}
```

### Constraints (all NON-negotiable for slice 0)
- No SQLite. No persistent registry. JSON export only.
- No authority migration. No plane-2 (`governor_execution`) fields populated.
- No production behavior changes. No playbook/gate consumption of the output yet.
- No deletion or rewrite of existing docs or of `.governor/backlog/*.json`.
- Conservative path/title heuristics; ambiguous files → `kind: "other"` + warning.
- Deterministic ordering and stable hashes (sort by `source_path`; content-hash file bytes).
- Output to `.governor/exports/state_index_export.v0.json` (rebuildable artifact).

### Acceptance criteria
- Running the exporter on the repo produces a byte-stable JSON artifact across repeated runs
  (deterministic ordering + hashes).
- Every scanned file yields exactly one record; unclassifiable files land as `other` with a warning.
- Every record carries `provenance_class`: `.governor/backlog/*.json` + `.governor/campaigns/*.yaml`
  → `declared`; everything scanned from prose → `observed`. Slice 0 never emits `execution`.
- Divergence between a `declared` item and its cited `spec_ref` prose (`observed`) surfaces as a
  warning with direction unattested (not a silent merge, not an overwrite, not an adjudication).
- Focused tests cover: gap classification, playbook/review classification, campaign
  status/next/decision files, working handoff/parked/exit files, deterministic ordering, stable
  source hashes, ambiguous-file fallback.
- Zero writes outside `.governor/exports/`.

### Files likely touched (slice 0)
- `src/governor/state_index_export.py` (scanner + record emit; boring, stdlib + existing deps)
- CLI entrypoint (`governor state-index export` under `cli.py` or the advanced group)
- `tests/test_state_index_export.py`

---

## Later slices (RECORDED, NOT AUTHORIZED)

- **Slice 1 — `.governor/state.sqlite` projection.** Ingest the export into SQLite. Append-only
  `state_events` + current-state `state_items` projection (git index + reflog shape). Rebuildable
  from the export. Tables sketch below. Carry `source_namespace` and the two planes from this
  slice's schema even if plane 2 stays empty.
- **Slice 2 — playbook consumption.** Playbooks query the projection for "what's next / ready /
  blocked." Read-only against the projection; admission still governed elsewhere.
- **Slice 3 — dependency closure / readiness checks.** `dependency_edges` + closure queries.
- **Slice 4 — multi-source import.** `source_repos`, freshness verdicts, import of foreign
  **exports** (not guts). Foreign rows reference-only unless a governed consumption rule allows more.
- **CI guard (cross-cutting).** Detect stale index vs docs divergence; warn, do not block authority.

### Eventual table sketch (slice 1+, illustrative)
```
source_repos(id, name, root_path, repo_fingerprint, trust_class, last_seen_commit)
state_items(id, source_namespace, external_id, kind, title, source_path, source_hash,
            project_status, gov_status, observed_at, updated_at)
state_events(event_id, item_id, event_type, payload_json, observed_at, source_path, source_hash)
dependency_edges(from_item_id, to_item_id, edge_kind, confidence, declared_by)
warnings(item_id, warning_code, message)
```

Likely-later files: `src/governor/state_registry.py`, `state_registry_scan.py`,
`playbooks/playbook_queue.py`, `review_packet.py`, `closure.py`, `digest.py`,
`handoff_renderer.py`, `tests/test_state_registry*.py`.

---

## Migration strategy — incremental, not a rewrite

1. **Slice 0: export only.** Read-only. Docs stay canonical. No behavior change. Proves the
   classification heuristics against the real corpus and surfaces prose↔`.governor/backlog`
   divergence.
2. **Slice 1: projection cache.** Import export into disposable SQLite. Still no authority.
3. **Slice 2+: consumption.** Playbooks read the projection. Admission stays governed.
4. **Multi-source last.** Only after single-namespace is boring and stable.

Adoption is validation-first: the export is checked *against* existing files, never a replacement
for them. The classic faceplant to avoid is "single tenant until Tuesday" — hence `source_namespace`
from schema v0.

---

## Open questions

- **ID stability.** Path-derived vs front-matter `id` vs the existing `.governor/backlog` `id`.
  Slice 0 should prefer an explicit front-matter/JSON `id` when present, else derive from path, and
  warn when a prose doc and a backlog item disagree on identity.
- **Status extraction.** How much status to infer from prose (fragile) vs require declared. Slice 0
  leans conservative: unknown status → `null` + warning, never a guess promoted to fact.
- **Where governor_execution status comes from.** Wicket? standing? run receipts? Deferred to
  Slice 1+; plane-2 columns stay empty until a governed admission writes them.
- **CI guard severity.** Warn-only vs block. Default warn (divergence is testimony, not a gate).

---

## Recommended next Codex task (Slice 0 only)

> Implement only Slice 0: `state_index_export.v0` in `agent_gov`. Add a read-only
> scanner/exporter for AG state-bearing planning docs. **No SQLite. No persistent registry. No
> authority migration. No production behavior changes. No playbook/gate consumption. No deletion or
> rewrite of existing docs or of `.governor/backlog/*.json`.**
>
> Scan: `specs/gaps/*.md`, `docs/playbooks/*.md`,
> `docs/campaigns/*/{CAMPAIGN,STATUS,NEXT,DECISIONS,INVENTORY,TRANSPORT}.md`,
> `docs/campaigns/*/GRANTS.yaml`, `working/*.md`, and `.governor/backlog/*.json`
> (the last as a *reconciliation input*: cross-check against cited `spec_ref` prose and emit a
> warning on divergence — do not overwrite it).
>
> Emit deterministic JSON records to `.governor/exports/state_index_export.v0.json` with fields:
> `schema`, `source_namespace` (`"ag"`), `provenance_class`, `id`, `kind`, `status`, `title`,
> `source_path`, `source_hash`, `warnings`. Tag `.governor/backlog/*.json` +
> `.governor/campaigns/*.yaml` as `provenance_class: "declared"` and everything scanned from prose as
> `"observed"`; never emit `"execution"`. Use conservative path/title heuristics; ambiguous files
> become `kind: "other"` with warnings; unknown status becomes `null` with a warning.
>
> Add focused tests: gap classification, playbook/review classification, campaign
> status/next/decision files, working handoff/parked/exit files, `provenance_class` tagging
> (declared vs observed), deterministic ordering, stable source hashes, ambiguous-file fallback, and
> prose↔backlog divergence warning.
>
> Hard rule to keep visible in the module docstring: **The export makes state legible; it does not
> make state true.**
