# Decisions — constellation reconciliation

Questions filed for operator ruling. A slice depending on an OPEN question is
blocked on it; everything else proceeds.

## Q-A7 — guvnah disposition  **(RULED 2026-07-02: RETIRE)**

**Operator decision: retire guvnah as the generic Governor cockpit.**

Rationale (operator, verbatim intent): guvnah solved a coordination problem the
local Governor tool did not yet have — a dashboard over a local, single-operator
daemon creates surface area before there is enough multi-case, multi-system
operational pressure to justify it.

- **No pin bump, daemon compatibility restoration, RPC coverage expansion, or
  feature work** for guvnah — ever, under this ruling.
- Disposition: archive or make private (operator-side); retained as
  **lineage/specimen material only**. Code, tests, RPC framing, and UI patterns
  may be borrowed later, but guvnah is **not** the active UI shell and **not the
  lineage authority for any successor**.
- Successor direction, if needed: greenfield **`nq-operator`** — an operations
  admissibility cockpit over NQ, Nightshift, AG, ticketing, and related casework
  surfaces. A **new product boundary**, not a revival of guvnah. (No repo, no
  slices, until its own forcing case — this is direction, not authorization.)

Effect on the register: guvnah leaves the open UI-shell verdict set; C2's
family question continues for phosphor / clerk / maude / vscode-governor /
thinkulator.

## Q-C2-1 — UI-shell family  **(RULED 2026-07-02, operator)**

guvnah: retire (see Q-A7) · maude: keep as operator TUI unless explicitly
superseded · phosphor: audit, then possibly retire or narrow to read/status ·
clerk: parked assistant shell · vscode-governor: parked IDE-specialized shell ·
thinkulator: nonfiction lane, not a Governor shell. Full table in
`docs/roadmaps/CONSOLIDATION.md` #1.

## Q-C2-* — remaining consolidation verdicts  **(OPEN: #2 wicket-guard, #5 read-plane trio)**

Created by slice C2 with recommendation and evidence. Custody-affecting (repo
boundaries are authority surfaces): operator fiat required per candidate; no
default action on silence. Operator pre-resolutions 2026-07-02 closed #1, #3,
#4, #6, #7, #8.

## Q-A5 — memory custody of relocation records  **(OPEN, low stakes)**

A5 corrects memory files: custody/cadence/dossier are parked in backburner;
clerk and the other UI shells live under ~/git/agent_gov_ui/. Should the
correction also add a standing memory rule "check ~/git/backburner and
~/git/agent_gov_ui before declaring a constellation repo nonexistent"? Default
on silence: yes, one line in MEMORY.md (cheap, prevents recurrence of the
agent-4 misread).
