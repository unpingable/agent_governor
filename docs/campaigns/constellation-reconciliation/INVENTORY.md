# Inventory — constellation reconciliation (prosecutor report)

**Status:** SKELETON (2026-07-02). Sections fill as slices land (see
[NEXT.md](NEXT.md)); A8 assembles the final report; A9 reviews it adversarially.
Nothing in this file authorizes anything.

## 1. Handoff surfaces found (A1 — executed 2026-07-02)

| path | exists | sha256-12 | last-commit | verdict/notes |
|------|--------|-----------|-------------|---------------|
| docs/REENTRY.md | YES | dc748b1f4a92 | 5bc6b8a 2026-07-01 | ✓ matches description; IDENTICAL bytes on main and this branch |
| working/linear-accountant-handoff.md | YES | e9e9455ba631 | 026603b 2026-06-03 | ✓ matches (§9 handoff-shape response) |
| docs/architecture/claim-custody-spine.md | YES | 50ba5bff657a | 5f7e87f 2026-06-10 | ✓ matches (receipt chain via GateReceiptSystem) |
| specs/gaps/GOV_GAP_STATE_REENTRY_PROTOCOL_001.md | YES | 96b8876cd854 | 3522b27 2026-05-03 | ✓ matches |
| docs/playbooks/live-adapter-allowlist-review.md | **NO (this branch)** | — | — | on conveyor branch only; superseded fossil w/ 11 inherited ration-card terms |
| src/governor/playbooks/handoff_renderer.py | **NO (this branch)** | — | — | on conveyor branch only (S6, `4022f22` LOCAL per REENTRY) |
| docs/playbooks/next-gate-selection-review.md | **NO (this branch)** | — | — | on conveyor branch only |
| docs/playbooks/* (9 further docs) | **NO (this branch)** | — | — | entire docs/playbooks/ dir is conveyor-branch content |

**Critical finding (branch visibility):** the playbook handoff surfaces exist
only on `feat/playbooks-synthetic-conveyor`; this branch and that one are
PARALLEL lanes (~46 conveyor commits not here; neither ancestor of the other).
`docs/REENTRY.md` is byte-identical on both branches **but references files
that exist only on the conveyor branch** — a reader on main-lineage branches
follows pointers into absence. Resolves at merge; until then REENTRY.md's
implicit claim "these paths exist" is true only on one lane. (Recorded, not
fixed — fixing = merging, which has its own checkpoint.)

Cross-references: all docs/roadmaps/README.md ↔ campaign ↔ tools/*.md links
resolve (17/17 tool files, 4/4 campaigns, ROUTING/PARKED/CONSOLIDATION).

Additional handoff-describing docs found (grep "handoff", not in the claimed
set): working/handoff-2026-07-02-roadmap-program.md, docs/constellation-zoning.md,
docs/interfaces/cli.md, docs/loop-protocol.md, docs/RECEIPT_SNAPSHOT_001.md,
docs/reference/internal-ops-glossary.md — swept by A2.

**Contradictions (verbatim, per stop condition):**
1. Campaign NEXT.md A1 says "docs/playbooks/handoff-renderer surfaces" (a docs/
   path); REENTRY.md line 56 places it at `handoff_renderer.py` (src). The
   docs/ path never existed — the slice text inherited an imprecise pointer.
2. The HandoffPacket seal contract ("content-sealed sha256(canonical_body),
   tamper-evident … NO authority-permitting surface") is documented **only in
   REENTRY.md prose** — no ratifiable spec doc describes the seal. Narrative
   custody of a load-bearing format. → feeds §4 minimal changes.

## 2. Stale or misleading language (A2, A7)

*(pending — findings table: file:line · quoted text · which distinguish-pair it
blurs. UI-pin drift rows from A7 land here.)*

## 3. Constellation doctrine mismatches (A3a/A3b, A4)

*(pending — Lean AG-AUDIT-CHECKLIST adjudication over extracted schema tables;
NQ BASIS_STALE_CONTRACT drift findings. Appendix: A3a mechanical tables.)*

## 4. Minimal changes recommended (A8)

*(pending — each entry separately committable, cited.)*

## 5. Do-not-build-yet list (A8)

Seeded from the campaign Forbidden section; grows only by evidence:

- Bounded autopilot (any form).
- Sandbox playbook promotion to operational use.
- NQ retirement-trigger wiring, stale-basis consumption logic, witness-clock
  adapter changes (named in tools/nq.md §4 as FUTURE build slices — not this
  campaign).
- UI pin bumps / shell revivals ahead of the Q-A7 / Q-C2 rulings.
- Any new refusal vocabulary not forced by a named mismatch.

## 6. Consolidation memo (C1 evidence, C2 adjudication)

*(pending — per-candidate evidence appendix + recommendations. Verdicts are
operator-only, recorded in DECISIONS.md.)*
