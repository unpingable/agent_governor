# Origin Mode

> **The model may propose; it may not mint standing, admit itself, spend twice, or cite what was never witnessed.**

`origin_mode` is the mint-provenance discriminator on every NQ `FindingSnapshot`. It is the closed-vocabulary answer to one question: did the producer observe this condition, or stage / replay / inject it?

Without this discriminator, a drill harness's manifest would be byte-identical to a real producer's manifest. With it, AG's `governor why` renders `DRILL` / `REPLAY` / `SYNTHETIC` on every node of a non-observed chain, and the operator cannot mistake the two.

## Two distinct axes

`origin_source` and `origin_mode` answer different questions and compose orthogonally. Both live on NQ; AG consumes both. (See `~/git/notquery/crates/nq-db/migrations/057_origin_mode_discriminator.sql`.)

- **`origin_source`** (NQ migration 046): **ingest path**. Closed set `{nq, import}`. Was this finding minted natively by NQ's evaluator pipeline, or ingested via the `nq.finding_import.v1` import wire?
- **`origin_mode`** (NQ migration 057): **mint provenance**. Closed set `{observed, drill, replay, synthetic}`. Did the producer observe this condition, stage it, replay it from a fixture, or synthesize it without a real condition?

A native NQ finding from authentic observation: `origin_source = 'nq'`, `origin_mode = 'observed'`. A drill harness emitting through the import path: `origin_source = 'import'`, `origin_mode = 'drill'`. Conflating these would let "I imported it" look like "I observed it" or vice versa.

## Closed vocabulary — `origin_mode`

(verbatim from NQ migration 057's CHECK constraint and AG's `src/governor/cooked_context_orchestrator.py::NQ_ORIGIN_MODES`)

- **`observed`** — producer authentically observed the condition.
- **`drill`** — staged condition; fire drill with a real smoke machine. The condition is operator-staged, the producer's observation of the staged condition is still mechanical and real, but the chain of causation is operator-authored.
- **`replay`** — replayed from a prior real observation (e.g. fixture playback against a fresh substrate).
- **`synthetic`** — fully synthetic; no real condition exists.

`observed` is the no-render-prefix case in `governor why` (`src/governor/why.py::NON_OBSERVED_RENDER_PREFIX`). The other three render as `DRILL` / `REPLAY` / `SYNTHETIC` uppercase prefixes on the chain output.

### AG-internal modes (separate axis, AG-minted)

For chains driven from AG-side stubs or operator CLI invocations without an upstream NQ finding, AG mints two internal `origin_mode` values (`src/governor/cooked_context_orchestrator.py::AG_INTERNAL_ORIGIN_MODES`):

- **`cli_origin`** — an operator invoked the chain at the CLI.
- **`stub_origin`** — a SPEC-honoring stub drove the chain (e.g., orchestrator harness with no NQ in the loop).

These are AG-owned and do not appear on NQ wire DTOs. Extending either set requires explicit ratification: D0c-b reopen for AG-internal modes, a coordinated NQ migration plus AG widening for NQ-side modes. AG does **not** invent NQ values unilaterally. The set `CLOSED_ORIGIN_MODES = AG_INTERNAL_ORIGIN_MODES | NQ_ORIGIN_MODES`; construction-time validation refuses any other value with `InvalidOriginModeError`.

## Why D0-Bridge existed — the custody gap

(filed at `working/nq-custody-gap-origin-discriminator.md`)

The AG provenance-field audit (2026-06-09) closed with recommendation D — NQ custody gap. NQ had no closed-vocabulary discriminator at finding mint distinguishing drilled / fault-injected / synthetic findings from authentic observations:

| Surface | File:line | Pre-057 state |
| --- | --- | --- |
| Storage CHECK | `nq-db/migrations/046_durable_artifact_substrate.sql:26-27` | `origin_source IN ('nq', 'import')` only — ingest path, not mint provenance |
| Wire DTO | `nq-db/src/export.rs:161` | `FindingOrigin.source` mirrored the closed set above |
| Import insertion | `nq-db/src/import.rs:339-343` | `visibility_state = 'observed'`, `origin_source = 'import'` hard-coded for every imported row |
| Producer string | `nq-db/src/detect.rs:461-466`, `export.rs:162` | free-form `basis_source_id` / `producer_id`; a consumer cannot trust a string-typed marker as a closed category |

A drill harness's manifest was therefore byte-identical to a real producer's manifest both at storage (`warning_state`) and on the wire (`FindingSnapshot.origin`). An AG demo that opened on a "live NQ alert" sourced from a drill manifest would re-enact, inside the demo, exactly the failure mode the demo was trying to refuse.

NQ migration 057 closed the gap by adding the `origin_mode` sibling column with the closed CHECK above. AG widened `CLOSED_ORIGIN_MODES` to the union, consumes the literal NQ value through the wire DTO verbatim, and renders DRILL / REPLAY / SYNTHETIC prefixes via the closed map in `src/governor/why.py`.

## Why AG-side fake provenance is laundering

AG does not invent `origin_mode` values that NQ did not mint. If an AG-side seam stamped `origin_mode=observed` on a chain driven from a drill manifest, that would be witness-layer laundering — exactly the failure mode `working/nq-custody-gap-origin-discriminator.md` exists to refuse.

The discipline (`src/governor/cooked_context_orchestrator.py`):

- The closed set is union-of-two-axes. The bridge uses the **concrete mint-provenance value** (`observed` / `drill` / `replay` / `synthetic`), **never** an umbrella alias like `nq_origin`. `InvalidOriginModeError` fires at construction for any value outside `CLOSED_ORIGIN_MODES`, including umbrella shapes.
- The `_OriginModeReceiptSink` wrapper injects the discriminator at emit time. Clients (`standing_client`, `wicket_client`, `linear_accountant_client`) are not modified; they call `sink.emit(...)` as before. The wrapper carries the value from the NQ wire DTO into every `evidence_bundle` en route.
- AG's `load_finding_snapshot_from_json` (`src/governor/drill_runner.py`) refuses with `InvalidFindingSnapshotError` if `origin_mode` is missing, is not in `NQ_ORIGIN_MODES`, or if the schema header is not `nq.finding_snapshot.v1`. No silent normalization. No best-effort substitution.
- NQ-side ratification is required for any vocabulary change. A coordinated migration plus AG widening — never AG-only.

The smoke machine is real. The alarm is real. The discriminator on the alarm tells you which one fired.

## Where the discriminator surfaces

- **In the wire DTO:** `FindingSnapshot.origin_mode` on the JSON emitted by `nq-monitor drill wal-bloat` (and on every production `serve` loop finding).
- **In AG's evidence bundles:** stamped into `evidence_bundle["origin_mode"]` on every emitted receipt by `_OriginModeReceiptSink`. The constant `EVIDENCE_KEY_ORIGIN_MODE` is the key.
- **In `governor why`:** the render walker reads `origin_mode` from the leaf receipt's `evidence_bundle` and prints the `DRILL` / `REPLAY` / `SYNTHETIC` prefix at the top of the chain output (`src/governor/why.py::render_text` + `NON_OBSERVED_RENDER_PREFIX`).
- **In the poster's DRILL paragraph:** the operator-facing string in `src/governor/drill_poster.py::DRILL_PARAGRAPH_BODY` reads `"origin_mode=drill minted at NQ; inherited by every downstream receipt; visible at every node via \`governor why <receipt-id>\`"`.
