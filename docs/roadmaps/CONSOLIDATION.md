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

## Overlap candidates (C1 gathers evidence per row; C2 adjudicates)

### 1. UI-shell family (richest target) — six operator surfaces over one daemon/CLI

guvnah (Electron RPC cockpit, 2026-02-24, pin **breaks** vs AG 2.8.1) ·
phosphor/gov-webui (web UI, 2026-03-28, pin 2.3.x) · clerk (parked Electron
assistant, working v0.1.0) · maude (TUI, 2026-04-07) · vscode-governor (parked IDE
extension v2.7.0) · thinkulator (parked spec, nonfiction lane).

Question for C2: how many operator surfaces does the constellation actually
sustain, and which one is canonical per modality (desktop / web / terminal / IDE)?
Evidence wanted: RPC-method coverage overlap (guvnah 39/88 vs phosphor 5/88 vs
maude), maintenance cost per shell, operator's actual usage. Prior signal:
maude is the governor's operator TUI by doctrine (memory: maude_dogfood_gap);
agent-4 called guvnah "deprecated" while agent-5 found a live-but-stale cockpit —
that conflict is itself evidence the boundary is undocumented.

### 2. wicket-guard → wicket

wicket-guard is pre-alpha (one commit, LICENSE-only cook) over the wicket kernel.
Question: does the diff→Intent cook earn a separate repo (criterion 2: different
consumers?) or is it a wicket `examples/`+module until it grows?

### 3. transition-kernel repo boundary vs AG in-repo kernel work

`~/git/transition-kernel` (Rust, 9-case byte-conformance, differential.py) vs AG's
in-repo transition-probe tests and the pickup campaign. Packet B (B0/B1/B3) already
reconciles content; the consolidation question is narrower: is the **repo boundary**
right? Prior signal says yes (criterion 1+2: Rust invariant-bearing kernel vs
Python control plane; rust_kernel_port_ruling), but C1 should verify the corpus
custody recommendation (B3) doesn't leave two masters.

### 4. receipt_kernel repo vs libs/receipt_kernel (in AG)

Same library in two places (standalone repo frozen 2026-03-14; in-tree
`libs/receipt_kernel` actively used). Question: retire one direction explicitly —
likely "in-tree is canonical, standalone is a fossil/extraction-candidate" — and
write it down so the next session doesn't re-derive it.

### 5. Read-plane trio: spine vs governor-atlas vs state_index_export

Three index/legibility surfaces: spine (constellation read plane, "findability is
not legitimacy"), governor-atlas (claim graph, specified-vs-wired docket),
state_index_export.v0 (AG prose→JSON projection). Likely verdict: genuinely
distinct scopes (constellation-wide reading / AG-architecture claims / AG-repo
state) — but the boundaries should be *written*, because all three will grow
toward each other.

### 6. wlp (live Rust wire protocol) vs wlp (backburner spec)

Name collision. Live `~/git/wlp` is healthy and v7-aligned; backburner "Witness
Ledger Protocol" (WLP-1 draft-4) is an older spec + Python ref impl. Adjudicate
lineage: rename the fossil, absorb as historical spec in the live repo, or
graveyard with LINEAGE note. (Two things answering to one name in a constellation
whose whole doctrine is unambiguous reference is a standing hazard.)

### 7. witness-stack (parked spec) vs AG receipt doctrine + wlp

Overlapping vocabulary claims about receipted operations. Question: does
witness-stack's grammar add anything the AG doctrine + wlp envelope don't already
own? If yes, cite it; if no, retire with pointer.

### 8. nlai (parked) vs AG in-tree claim_signals / evidence_gate

AG grew claim extraction in-tree after nlai parked. Question: any capability in
nlai v0.3.0 worth harvesting (sentence-level extraction?) before marking it
absorbed. Harvest-then-retire is a legitimate verdict.

## Non-goals

- No merges, renames, or archive moves from this register directly.
- No treating "stale" as "absorb" — staleness is evidence, not a verdict
  (see PARKED doctrine: parked ≠ worthless).
- No consolidating *concepts* (cadence/custody vocabulary in AG stays regardless
  of repo verdicts).
