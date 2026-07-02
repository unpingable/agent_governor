# Decisions — constellation reconciliation

Questions filed for operator ruling. A slice depending on an OPEN question is
blocked on it; everything else proceeds.

## Q-A7 — guvnah disposition  **(OPEN)**

guvnah (Electron cockpit, v2.3.2, 2026-02-24) is hard-pinned `>=2.3.2 <2.4.0` and
**breaks** against AG 2.8.1. Exploration produced conflicting readings
("deprecated/superseded" vs "stale but doctrinally-correct cockpit, 39/88 RPC
wired"). Options: (a) revive + re-pin + wire deferred namespaces; (b) retire
explicitly with pointer to a surviving shell; (c) defer to the UI-shell
consolidation verdict (C2). **Recommendation: (c)** — one ruling for the whole
shell family beats three piecemeal ones. Blocks: ratification of
`docs/roadmaps/tools/guvnah.md` §4 build slices only.

## Q-C2-* — consolidation verdicts  **(NOT YET FILED)**

One entry per CONSOLIDATION.md candidate, created by slice C2 with its
recommendation and evidence. Custody-affecting (repo boundaries are authority
surfaces): operator fiat required per candidate; no default action on silence.

## Q-A5 — memory custody of relocation records  **(OPEN, low stakes)**

A5 corrects memory files to say custody/cadence/dossier/clerk are parked in
backburner. Should the correction also add a standing memory rule "check
~/git/backburner before declaring a constellation repo nonexistent"? Default on
silence: yes, one line in MEMORY.md (cheap, prevents recurrence of the agent-4
misread).
