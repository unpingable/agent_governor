# Status — constellation reconciliation

As of 2026-07-02.

## Done

- Campaign filed as part of the roadmap-of-roadmaps program setup
  (branch `feat/roadmaps-constellation`). Evidence base: six-agent exploration
  sweep 2026-07-02.
- **A6 executed with program setup** (ROADMAP.md supersession rewrite — landed as
  its own commit in the setup sequence; A8 cites it).

## 2026-07-02 (later) — operator pre-resolutions after skim + external review

- Consolidation candidates resolved by operator action/ruling: #1 UI-shell
  family (**Q-C2-1**: guvnah retire / maude keep as operator TUI / phosphor
  audit-then-retire-or-narrow / clerk + vscode-governor parked shells /
  thinkulator reclassified nonfiction-lane), #3 transition-kernel boundary (keep
  separate — core-separation ratification), #4 receipt_kernel (parked; in-tree
  canonical), #6 two-wlps (fossil renamed `witness-ledger-protocol` + LINEAGE,
  executed), #7 witness-stack (graveyarded), #8 nlai (stays parked).
  **C1/C2 scope shrinks to #2 (wicket-guard, inclination: absorb into wicket)
  and #5 (read-plane trio).**
- **Q-A7 RULED: guvnah RETIRED** (specimen/lineage only; no pin bump, no compat
  work; successor direction = greenfield `nq-operator`, a new product boundary).
- UI shells regrouped under `~/git/agent_gov_ui/`; backburner roster now 9.
- R-MAUDE-2 (resync maude to current daemon) unblocked by the ruling.
- **Q-C2-1 AMENDED same evening:** maude reframed as terminal-native operator
  shell (OpenClaw/Hermes-shaped; exits the Governor-shell bucket; R-MAUDE-3
  product-boundary conversation deferred); phosphor reframed as web-native lane
  host with candidate `ops-casework` lane (R-PHOS-0 executed / R-PHOS-1 audit /
  R-PHOS-2 lane design, Fable+operator-paired / R-PHOS-3 build) — supersedes
  the morning's retire-or-narrow. `nq-operator` demoted to future-possibility
  (only if the lane outgrows the shell).
- **Push checkpoint (operator):** everything pushes after step 5 of the
  execution order (i.e. after B4 lands) — not before.
- Nits from external review patched: C1 candidate cardinality, wlp.md numbering,
  nq.md HEAD (bumped to `59616dc` — NQ moved again since the sweep).

## Current next

A1 (surface-inventory verification) and the independent slices A3a/A4/A5/A7/C1
are unblocked. See [NEXT.md](NEXT.md) for order and routing.

## Not started

A2, A3b, C2, A8, A9 (blocked per prereq graph).

## Notes

- `docs/REENTRY.md` verified present on main 2026-07-02 (`git show
  main:docs/REENTRY.md` exits 0); the earlier "phantom" report was
  branch-visibility confusion. A1 records the hash.
- Memory-side edits in A5 (files under `~/.claude/projects/.../memory/`) are
  outside the repo; record their completion here when done.
