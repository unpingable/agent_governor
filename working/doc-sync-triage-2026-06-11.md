# Doc-Sync Triage — Undocumented AG Surface (T2)

**Status: EXECUTED 2026-06-11.** T2a–T2d landed in the same pass the operator
greenlit. Result: `file-structure.md` now documents **0/176** undocumented
governor modules (all 75 added, grouped by concern, experimental fenced);
`cli-reference.md` gained the ~40 missing command groups/aliases. The 5 CONFIRM
leaves all resolved to real modules (none dead). The buckets/table below are kept
as the decision record; the "Recommended slices" are done except the optional
AG-internal format pass (gap-spec template consistency), which remains available.

**Original status (for the record): triage artifact for operator decision.** Filed 2026-06-11.
Produced from a grounded survey pass (T1 factual corrections already landed; see
bottom). This table is the input to the actual doc-update slices, not the update
itself. Per `feedback_completion_redshift`: grounded in files + signals, not vibes.

## The reframe (where the drift actually is)

The raw finding was "~77 governor modules undocumented." Grounded, it's **75 of
176 top-level `src/governor/*.py` modules with no line in `file-structure.md`** —
but two facts shrink the alarm:

1. **Nearly all 75 have a dedicated `tests/test_<name>.py`.** This is tested,
   shipped code, not scaffolding-in-flight. (Only 4 lack a test file: `why`,
   `status_rollup`, `cli_friendly`, `drill_runner`.)
2. **Many are already in `feature-history.md` by *feature name*** (MCP Safety →
   `mcp_safety`, SDK Middleware → `sdk`, External Constraint Attachment →
   `external`, Prometheus Metrics → `prometheus`, etc.). The filename-match survey
   missed these because feature-history describes by prose, not path.

So the drift is concentrated in the **two structural maps**, not the feature
catalog:

- `file-structure.md` — the module tree (missing ~75 file lines).
- `cli-reference.md` — the CLI map (documents 44 groups; ~25–30 top-level groups
  shipped-but-undocumented).

`feature-history.md` is in good shape (T1 fixed its one real error, the receipt-
kernel invariant count). That's the benign completion-redshift signature: the
*narrative* of what was built is roughly current; the *indexes* lag.

## Signal table (the 75 undocumented modules)

Columns: `cli` = referenced from `cli*.py` (has/feeds a CLI surface); `impBy` =
count of other governor modules importing it (substrate depth); `test` = has
`tests/test_<name>.py`; `LOC`. None appears in `file-structure.md`. Sorted by
wiring depth.

```
module                        cli impBy test  LOC    disposition
overrides                      Y   6    Y     465    DOC (governance; live)
autopilot                      Y   4    Y     414    DOC (control/tuning)
constraint_compiler            Y   4    Y    1381    DOC (governance core)
control_theory                 Y   4    Y    1354    DOC (control/tuning)
staleness                      Y   4    Y     446    DOC (telemetry)
docket                         Y   3    Y     654    DOC (governance)
evidence_store                 Y   3    Y     387    DOC (evidence)
operator_snapshot              Y   3    Y     443    DOC (operator/observability)
status_rollup                  Y   3    .     264    DOC (observability; no test)
admissibility                  Y   2    Y     480    DOC (governance core; `admit`)
claim_status                   Y   2    Y     332    DOC (governance)
coherence_budget               Y   2    Y     643    DOC (control/budget)
commitment_transport           Y   2    Y     933    DOC (transport; `transport`)
constraint_gate                Y   2    Y     375    DOC (governance core)
dashboard_ux                   Y   2    Y     718    DOC (observability; `dashboard-ux`)
deployment_profiles            Y   2    Y     508    DOC (config; `deploy`)
detector_integration           Y   2    Y     782    DOC (diagnostics; `detector`)
doc_governance                 Y   2    Y     880    DOC (governance; `doc`)
epistemic_evasion              Y   2    Y     590    EXPERIMENTAL (`evasion`)
gate_heartbeat                 Y   2    Y     214    DOC (observability)
hysteresis                     Y   2    Y     482    DOC (control; `hysteresis`)
instrument                     Y   2    Y    1971    DOC (observability; `instrument`)
measurement_integrity          Y   2    Y     415    DOC (observability; `measure`)
metrics                        Y   2    Y     426    DOC (observability; `metrics`)
mode_detection                 Y   2    Y     436    DOC (governance)
phase_control                  Y   2    Y     493    DOC (governance; `phase`)
quorum_ext                     Y   2    Y     622    DOC (governance; `quorum-ext`)
release_taint                  Y   2    Y     292    DOC (provenance)
replay                         Y   2    Y     677    DOC (telemetry/replay)
reservations                   Y   2    Y     345    DOC (governance/leases)
risk_function                  Y   2    Y     509    DOC (governance; `risk`)
scalar_collapse                Y   2    Y     873    DOC (control; `collapse`)
selfcheck                      Y   2    Y     268    DOC (QA; `selfcheck`)
slim_mode                      Y   2    Y     518    DOC (context; `slim`)
spectral_stability             Y   2    Y     891    EXPERIMENTAL (`stability`)
temporal_attack                Y   2    Y     618    EXPERIMENTAL (`temporal`)
webui_demo                     Y   2    Y     535    DOC (demo-tagged)
why                            Y   2    .     619    EXPERIMENTAL (`why`; no test)
codex_hooks                    Y   1    Y     389    DOC (constellation adapter)
config_effective               Y   1    Y     361    DOC (config)
doctrine                       Y   1    Y     336    DOC (governance; `doctrine`)
external                       Y   1    Y     870    DOC* (in feature-history)
oracle_pytest                  Y   1    Y     397    DOC (evidence/oracle)
preflight                      Y   1    Y     638    DOC (governance; `preflight`)
prometheus                     Y   1    Y     664    DOC* (in feature-history)
trace_recorder                 Y   1    Y     125    DOC (observability)
capture                        Y   0    Y     992    DOC (correlator/observability)
policy_engine                  .   6    Y    1008    DOC (substrate; deep dep)
linear_accountant_client       .   4    Y     853    DOC (constellation adapter — HIGH)
chrono                         .   2    Y     171    DOC (time helper)
cli_backend                    .   2    Y     302    DOC (CLI infra; `backend`)
cli_chat                       .   2    Y     675    DOC (CLI infra; `chat`)
cli_operator                   .   2    Y     675    DOC (CLI infra)
cooked_context_orchestrator    .   2    Y     520    DOC (context)
identity                       .   2    Y     354    DOC (substrate)
standing_client                .   2    Y     371    DOC (constellation adapter — HIGH)
wicket_client                  .   2    Y     500    DOC (constellation adapter — HIGH)
chain_gate                     .   1    Y    1147    DOC (governance core)
claim_correlation              .   1    Y     744    DOC (analysis)
cli_group                      .   1    Y      72    DOC (CLI infra)
nightshift_adapter             .   1    Y     742    DOC (constellation adapter — HIGH)
policy_ir                      .   1    Y     637    DOC (governance/IR)
receipt_v1_bridge              .   1    Y     366    DOC (receipt substrate)
research_store                 .   1    Y     673    EXPERIMENTAL (research)
cli_friendly                   .   1    .    1079    DOC (CLI infra; no test)
drill_runner                   .   1    .    2049    DOC? (drills; no test — CONFIRM)
clud                           .   0    Y     588    DOC (CLUD clarity sensor — has docs/)
detector_handoff               .   0    Y     642    CONFIRM (leaf; entry-point?)
drill_poster                   .   0    Y     933    EXPERIMENTAL/drills (CONFIRM)
governed_dispatch              .   0    Y     310    CONFIRM (leaf; unwired?)
mcp_safety                     .   0    Y     922    DOC* (in feature-history)
plan_review                    .   0    Y     806    CONFIRM (leaf; entry-point?)
research_why                   .   0    .     209    EXPERIMENTAL (research; no test)
sdk                            .   0    Y     600    DOC* (in feature-history — entry-point)
session_store                  .   0    Y     231    CONFIRM (leaf; vs session.py?)
```

`*` = already described in `feature-history.md` by feature name; only the
`file-structure.md` line is missing (cheapest to fix — link, don't re-describe).

## Buckets and disposition

**Bucket A — DOCUMENT in `file-structure.md` (and `cli-reference.md` where
CLI-wired).** The large majority (~55 modules): tested, wired, real platform or
substrate. Subgroups for the file-map slice:

- **Constellation adapters (HIGH value — "everything flows out from AG"):**
  `standing_client`, `wicket_client`, `linear_accountant_client`,
  `nightshift_adapter`, `codex_hooks`, `external`, `receipt_v1_bridge`. These wire
  AG to sibling repos; given the operator's "AG is the headwaters" framing, these
  are the highest-leverage to surface. Do first.
- **Governance core:** `admissibility`, `chain_gate`, `constraint_compiler`,
  `constraint_gate`, `policy_engine`, `policy_ir`, `claim_status`, `docket`,
  `doctrine`, `overrides`, `reservations`, `risk_function`, `mode_detection`,
  `coherence_budget`, `preflight`, `phase_control`, `quorum_ext`, `doc_governance`.
- **Observability / telemetry / diagnostics:** `metrics`, `prometheus`,
  `gate_heartbeat`, `instrument`, `measurement_integrity`, `status_rollup`,
  `operator_snapshot`, `dashboard_ux`, `trace_recorder`, `capture`,
  `detector_integration`, `hysteresis`, `staleness`, `selfcheck`, `replay`,
  `claim_correlation`.
- **CLI infrastructure:** `cli_backend`, `cli_chat`, `cli_operator`, `cli_group`,
  `cli_friendly` (document as the CLI's own module structure).
- **Control / tuning:** `autopilot`, `control_theory`, `scalar_collapse`,
  `chrono`, `coherence_budget`.
- **Evidence / context / misc substrate:** `evidence_store`, `oracle_pytest`,
  `cooked_context_orchestrator`, `commitment_transport`, `release_taint`,
  `identity`, `config_effective`, `deployment_profiles`, `slim_mode`,
  `webui_demo` (demo-tag), `clud`.

**Bucket B — DOCUMENT with an EXPERIMENTAL / research tag** (don't present as
stable platform; this is the scaffolding-vs-stable distinction the survey
flagged): `epistemic_evasion`, `temporal_attack`, `spectral_stability`, `why`,
`research_store`, `research_why`, `drill_poster`, `drill_runner`. Most have CLI
surfaces (`evasion`, `temporal`, `stability`, `why`) — so they're *reachable*,
which is the argument for documenting-with-a-warning rather than hiding. Decision
needed: do these belong in `cli-reference.md` at all, or behind an "experimental
commands" subsection?

**Bucket C — CONFIRM before documenting (low-wiring leaves, role unclear):**
`detector_handoff`, `governed_dispatch`, `plan_review`, `session_store`,
`drill_runner`. `impBy=0` + no CLI means either an entry-point (invoked by tests /
external / a subpackage not scanned) or an orphan. `session_store` specifically
wants disambiguation against the documented `session.py` / `session_continuity.py`.
Quick human ID (or one more grep pass) resolves these; none is confidently dead —
all but `research_why` have tests and substantial LOC.

**`cbi` / `kernel` CLI groups** appear in the command extraction but didn't map
cleanly to a module here — confirm what backs them before documenting.

## CLI map drift (`cli-reference.md`)

Documents 44 top-level `governor <group>` commands. Undocumented top-level groups
(noise-filtered from the raw extraction, which also caught subcommands like
`add`/`remove`/`lock`/`anchor`): roughly **25–30**, including `admit`, `backend`,
`cbi`, `chat`, `codex-hooks`, `collapse`, `constraint(s)`, `dashboard-ux`, `demo`,
`deploy`, `detector`, `doc`, `doctrine`, `evasion`, `hysteresis`, `instrument`,
`kernel`, `measure`, `metrics`, `phase`, `preflight`, `quorum-ext`, `risk`,
`selfcheck`, `slim`, `stability`, `temporal`, `transport`. A precise group-vs-
subcommand resolution is part of the slice itself (don't trust the raw 51).

## Recommended slices (operator greenlights / sequences)

Sized small, each independently committable:

- **T2a — Constellation-adapter file-map lines (smallest, highest leverage).**
  Add the 7 adapter modules + the `*`-tagged feature-history-known modules
  (`mcp_safety`, `sdk`, `external`, `prometheus`) to `file-structure.md`. ~11
  one-liners. Surfaces the "AG → constellation" wiring that's currently invisible.
- **T2b — Full `file-structure.md` module sweep.** Add the remaining Bucket A
  modules with one-line inventory notes (mirror existing house style). Hold
  Bucket B behind an "Experimental / research" subsection; hold Bucket C pending
  CONFIRM.
- **T2c — `cli-reference.md` group sweep.** Resolve groups-vs-subcommands, add the
  ~25–30 missing groups. Decide Bucket B's placement (experimental subsection).
- **T2d — Bucket C disambiguation.** Five modules, one grep/human pass; document or
  flag-for-removal.
- **Format pass (AG-internal, rides T2b/T2c):** while in the maps, check the 92
  `specs/gaps/` files share one template and `working/` notes carry a consistent
  status header. AG-owned; produces a template that can be *offered* (not imposed)
  to sibling repos via the existing internal-ops glossary / constellation lexicon
  rails. Do NOT open a cross-repo format sweep (see `constellation_constraint`,
  `parked_constellation_alignment_pass`).

T3 (gap-spec status sweep, `working/` archive of ~12 closed files) stays deferred;
the gap-spec part already has a disposition in `working/gap-backlog-triage-2026-06-10.md`.

## T1 — already landed this pass (factual corrections)

- `CLAUDE.md`: test count `~14,500` → `~15,400` (15,400 collected 2026-06-11).
- `feature-history.md` + `file-structure.md`: receipt-kernel "**6 constitutional
  invariants**" → **13 in 3 groups** (structural 6 / hallucination 6 / oracle 1).
  This surfaced a whole shipped anti-hallucination invariant group that the
  catalog had hidden — the sharpest single completion-redshift error found.
