# CONSOLIDATION lane — overlap register and absorption criteria

**Status:** CANDIDATE REGISTER (2026-07-02). Nothing here is decided. Evidence is
assembled by slice C1, adjudicated into a recommendation memo by slice C2 (see
`docs/campaigns/constellation-reconciliation/NEXT.md`), and **ruled one-by-one by
the operator** — repo boundaries are authority surfaces, so consolidation verdicts
are custody-affecting. This file never executes a merge.

## Criteria (from existing doctrine)

Separation of two surfaces earns its keep **only** when at least one holds:

1. **Distinct authority surface** — the repos mint/refuse different things, or one
   must not be able to forge the other's testimony (contamination firewall).
2. **Distinct implementation surface** — different language/runtime/release
   cadence where co-residence would couple what must version independently.
3. **Distinct contamination surface** — independent derivation matters (e.g.
   review independence, witness independence).

Default is SHARED. "It felt like a separate thing at the time" is not a criterion.
Corollary: absorption must not launder authority — merging a testimony surface
into an authority surface needs an explicit boundary note inside the merged repo.

**Ratified (operator, 2026-07-02): the core surfaces stay separate.** NQ
(evidence/basis lifecycle), Standing (grant/authority standing), LA (consumable
capacity/spend), Wicket (context authorization verdict), Lean (formal proof
surface), transition-kernel (Rust invariant-bearing kernel), wlp (envelope wire
protocol), verifier (constraint checking, not governance), claimc (settleability,
not truth) — distinct authority or implementation surfaces; merging would create
more laundering risk than cleanup. Candidates below re-open only on new evidence.

## Overlap candidates (C1 gathers evidence for OPEN rows; C2 adjudicates)

### 1. UI-shell family — six operator surfaces over one daemon/CLI  **(RULED 2026-07-02, operator)**

Regrouped under **`~/git/agent_gov_ui/`** (clerk · gov-webui · guvnah · maude ·
vscode-governor; thinkulator spec-only in backburner), then ruled per shell:

| shell | disposition (as amended same day) |
|---|---|
| guvnah | **RETIRE** (Q-A7 — lineage/specimen only; was "dashboard for a local Governor" — premature surface area) |
| maude | **KEEP + REFRAME**: terminal-native operator shell for supervised agent runtimes (OpenClaw/Hermes-shaped); AG = one authority substrate it invokes. **Exits the Governor-shell bucket** — see tools/maude.md §0 |
| phosphor (gov-webui) | **KEEP + REFRAME**: web-native lane host (focused workflow lanes, not universal daemon control); candidate `ops-casework` lane over NQ/Nightshift/AG/ticketing. Audit (R-PHOS-1) → lane design (R-PHOS-2) → build. See tools/phosphor.md §0 |
| clerk | parked assistant shell (kept, inactive) |
| vscode-governor | parked IDE-specialized shell (kept, inactive) |
| thinkulator | nonfiction-lane product spec — **not a Governor shell** (leaves this family) |

The resulting product split (operator + external review, 2026-07-02):

```
maude       = terminal-native agent/runtime operator shell (runs the room)
phosphor    = web-native lane host (ops-casework lane = near-term ops cockpit)
AG          = authority kernel + receipts + refusal semantics (decides what the
              room is allowed to claim)
nightshift  = operational policy / unsettled-claim layer
NQ          = evidence/basis testimony
nq-operator = possible FUTURE standalone ops cockpit, only if the phosphor lane
              outgrows the shell (one of them at a time, not both)
```

Boundary rule (both shells): shells orchestrate and render; they must not become
authority sources. AG refuses/authorizes authority-bearing transitions; it must
not become the runtime. No new shells; any future operator cockpit starts as its
own product boundary with its own record.

### 2. wicket-guard → wicket  **(OPEN, operator inclination recorded)**

wicket-guard is pre-alpha (one commit, LICENSE-only cook) over the wicket kernel.
Question: does the diff→Intent cook earn a separate repo (criterion 2: different
consumers?) or is it a wicket `examples/`+module until it grows?
Operator inclination (2026-07-02): "not sure why wicket-guard exists" — absorb
into wicket (e.g. `wicket/examples/`). Execution awaits an explicit go (the move
touches wicket's repo, a sibling authority surface).

### 3. transition-kernel repo boundary vs AG in-repo kernel work  **(RESOLVED 2026-07-02: keep separate)**

Covered by the core-separation ratification above (criterion 1+2: Rust
invariant-bearing kernel vs Python control plane). Residual: B3's corpus-custody
ruling (Q-B3) must not leave two masters — tracked in the pickup campaign.

### 4. receipt_kernel repo vs libs/receipt_kernel (in AG)  **(RESOLVED 2026-07-02)**

Operator: the standalone repo was a PyPI self-promotion experiment (like nlai);
now parked in `~/git/backburner/receipt_kernel`. **In-tree `libs/receipt_kernel`
is canonical.** Re-extraction FROM in-tree is the only future path if an external
consumer appears.

### 5. Read-plane trio: spine vs governor-atlas vs state_index_export  **(OPEN)**

Three index/legibility surfaces: spine (constellation read plane, "findability is
not legitimacy"), governor-atlas (claim graph, specified-vs-wired docket),
state_index_export.v0 (AG prose→JSON projection). Likely verdict: genuinely
distinct scopes (constellation-wide reading / AG-architecture claims / AG-repo
state) — but the boundaries should be *written*, because all three will grow
toward each other.

### 6. wlp (live Rust wire protocol) vs wlp (backburner spec)  **(RESOLVED 2026-07-02: fossil renamed)**

Name collision, intolerable under unambiguous-reference doctrine. Operator
authorized the fix; executed same day: `~/git/backburner/wlp` →
`~/git/backburner/witness-ledger-protocol`, with an in-repo LINEAGE.md (commit
`ee88cf5`) recording the collision and pointing at the live `~/git/wlp`. The
fossil stays parked as a historical spec — convergent name, different design,
not superseded-by.

### 7. witness-stack (spec) vs AG receipt doctrine + wlp  **(RESOLVED 2026-07-02: graveyarded)**

Operator moved witness-stack to `~/git/graveyard/` (spec-only, no remote). Its
receipted-ops vocabulary is owned by AG doctrine + the wlp envelope; anything
citing witness-stack cites the graveyard copy as historical.

### 8. nlai (parked) vs AG in-tree claim_signals / evidence_gate  **(RESOLVED 2026-07-02: stays parked)**

Operator: nlai (like receipt_kernel) was a PyPI self-promotion experiment; it
stays in backburner. Harvest question closed — reopens only with a fresh forcing
case naming a capability the in-tree modules lack.

## Non-goals

- No merges, renames, or archive moves from this register directly.
- No treating "stale" as "absorb" — staleness is evidence, not a verdict
  (see PARKED doctrine: parked ≠ worthless).
- No consolidating *concepts* (cadence/custody vocabulary in AG stays regardless
  of repo verdicts).
