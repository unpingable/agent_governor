# Roadmap — guvnah × AG

**Status:** RATIFIED (2026-07-02 — Q-A7 RULED: **RETIRED**)
Repo: `~/git/agent_gov_ui/guvnah` (HEAD `f58fd49`, 2026-02-24; v2.3.2 Electron
cockpit) · Docket: governor-atlas constellation case · Ruling:
`docs/campaigns/constellation-reconciliation/DECISIONS.md` Q-A7

## 1. Disposition (operator ruling, 2026-07-02)

**Retired as the generic Governor cockpit.** guvnah solved a coordination
problem the local Governor tool did not yet have; a dashboard over a local,
single-operator daemon creates surface area before multi-case, multi-system
operational pressure justifies it. Archive or make private (operator-side);
retained as **lineage/specimen material only** — code, tests, RPC framing, and
UI patterns may be borrowed later, but guvnah is not the active UI shell and
**not the lineage authority for any successor**.

Successor direction, if needed: greenfield **`nq-operator`** — an operations
admissibility cockpit over NQ, Nightshift, AG, ticketing, and related casework
surfaces. A new product boundary, not a revival. No repo, no slices, until its
own forcing case.

## 2. Specimen record (what it was — for future borrowing)

- Electron 33 / Svelte 5 over the daemon as a stdio child (Content-Length framed
  JSON-RPC 2.0); untrusted-cockpit doctrine (governor sole authority; IPC
  shape-adapters as the single compat seam; per-panel error isolation) — the
  doctrine was correct even where the product wasn't needed.
- 39/88 RPC methods wired; 16 documented not-wired; 123 unit tests + 2 E2E.
- Hard pin `>=2.3.2 <2.4.0` (breaks vs AG 2.8.1) — left as-is by ruling.

## 3. Slices

None. Retired.

## 4. Do-not-build

- No pin bump, no daemon compat restoration, no RPC expansion, no feature work
  (ruling, verbatim).
- No `nq-operator` work smuggled in under this file — that is a new product
  boundary with its own future record.

## 5. Operator questions

None. Q-A7 ruled.
