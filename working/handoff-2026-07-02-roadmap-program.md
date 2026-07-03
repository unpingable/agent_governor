# Session handoff — roadmap program + governed shell (2026-07-02)

Cold-start entry point for the NEXT session (any model tier; slices below are
routed per `docs/roadmaps/ROUTING.md`). Everything stated here is backed by
committed docs — when in doubt, the doc wins over this note.

## Where things stand

- **Branch `feat/roadmaps-constellation`** (off main, **UNPUSHED**, 19 commits
  ending `5532df1`). Holds the whole roadmap program. **Push checkpoint
  (operator): push only after B4 lands** (pickup campaign step 5) — do not
  push before.
- Branch `feat/playbooks-synthetic-conveyor` — separate lane, pushed, NEXT=S6
  (untouched today).
- Three campaigns live:
  1. `docs/campaigns/constellation-reconciliation/` — Packet A (A1–A9 +
     C1–C2). Not started; A1/A3a/A4/A5/A7/C1 unblocked.
  2. `docs/campaigns/transition-kernel-pickup/` — Packet B resumed (B-series).
     B4 (=Slice 1b) gated ONLY on **Q-B1: operator confirm+push of Standing
     commits `1e62ba9`/`f101c55`** (local-only — custody hazard).
  3. `docs/campaigns/governed-shell/` — GS-0/GS-1 done (design + contract);
     GS-2..GS-6 unblocked.
- Hub: `docs/roadmaps/README.md` (17 tool roadmaps, PARKED 9, CONSOLIDATION
  register mostly pre-ruled — open: #2 wicket-guard, #5 read-plane trio).
- Root `ROADMAP.md` is a supersession pointer (intentional).

## Operator rulings already made (do NOT re-litigate)

(This note is a SUMMARY, not the decision record — the rulings live in the
three campaign DECISIONS.md files and bind from there; if this summary and a
DECISIONS file disagree, the DECISIONS file wins. Same for the push rule
below: operator utterance 2026-07-02, recorded in reconciliation STATUS.)

Q-A7 guvnah RETIRED (specimen only) · Q-C2-1 amended: maude = terminal
operator shell (adapters STAY AG), phosphor = web lane host (+ ops-casework
lane candidate) · core repo separation ratified · two-wlp collision fixed
(`backburner/witness-ledger-protocol`, LINEAGE `ee88cf5`) · governed-shell:
queue-first, chat cut from maude v3, LaneSpec new-lanes-only, widening offers
PARKED (AG-minted only, ever). Open decisions live ONLY in the three
DECISIONS.md files (Q-B1, Q-B3, D-GS-6 naming, D-GS-7 reattach verify-first).

## Next work orders by tier (pick per available model)

**Mechanical (codex or local-qwen — full work orders in the NEXT.md files):**
- A1 surface-inventory verification (reconciliation NEXT.md) — pure read+hash.
- A3a Lean-checklist schema extraction — pure read, tables out.
- C1 consolidation evidence (now only candidates #2 + #5) — pure read.
- B1 three-world inventory diff (pickup NEXT.md) — runs
  `~/git/transition-kernel/scripts/differential.py`, records real exit code.
- GS-2 `operator.decisions.list` + docket/admissibility reads (governed-shell
  NEXT.md; implements `docs/design/governed-shell/shell-contract-v0.md` §2;
  new file `src/governor/operator_decisions.py` + tests) — codex tier, has a
  codex-exec review checkpoint after.
- GS-6 exposure batch (why.chain / adapters.list / probe state) — parts
  local-qwen eligible.
- R-VER-1, R-MAUDE-1, R-PHOS-1 (tool roadmaps §4) — read-only audits.

**Review (codex-exec):** A2 distinguish-pairs sweep (rubric in slice text).

**Conceptual (Fable / operator-paired — do NOT hand to small models):**
A3b, A4, C2, A8, B0-done, B2, B3, GS-3's design half, R-PHOS-2 content half.

**Small-model rules (ROUTING.md §3, enforced):** acceptance commands verbatim,
files enumerated, NO vocabulary minting, on any surprise STOP and write
`working/obstruction-<slice-id>.md` — never improvise. Slices touching
mint/spend/refusal-placement/admission are sandwiched (conceptual → mechanical
→ mandatory codex-exec review).

## Standing hazards for a cold session

- Exporter (`state_index_export.py`) lives on the CONVEYOR branch, not here —
  verification runs it extracted (see gap spec
  `GOV_GAP_ROADMAP_INDEX_LEGIBILITY_001.md` §cross-branch).
- Constellation membership fence: hub table + PARKED.md only; check
  `~/git/backburner` and `~/git/agent_gov_ui/` before declaring repos
  missing/moved; writing archives are NOT members.
- NQ moves fast — re-verify its HEAD before citing (was `59616dc` today).
- No push during work hours; no push at all before the B4 checkpoint.
