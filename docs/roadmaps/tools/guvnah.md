# Roadmap — guvnah × AG

**Status:** DRAFT (2026-07-02; §4 build slices blocked on Q-A7)
Repo: `~/git/guvnah` (HEAD `f58fd49`, 2026-02-24; v2.3.2 Electron cockpit) ·
Docket: governor-atlas constellation case

## 1. Contract snapshot — what AG assumes today

- Electron 33 / Svelte 5 cockpit over the daemon as a **stdio child**
  (Content-Length framed JSON-RPC 2.0); untrusted-cockpit doctrine (governor is
  sole authority; IPC shape-adapters are the single compat seam; per-panel error
  isolation).
- 39/88 RPC methods wired (chain/claims/commit/correlator/governor/intent/
  operator/receipts/receipts_v1/scars/sessions/trace); 16 documented NOT wired
  (scope, stability, lanes, policy, chat — chat intentionally: observe-only).
- COMPAT.md pin: **`>=2.3.2 <2.4.0`** — refuses newer daemons by design.
- 123 unit tests + 2 Playwright E2E.

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| Hard pin `<2.4.0` vs AG 2.8.1 = **breaking**: guvnah cannot start against the current daemon | guvnah COMPAT.md; AG pyproject 2.8.1 | BREAKING |
| Exploration produced conflicting dispositions: "deprecated/superseded" vs "stale but doctrinally-correct cockpit" — the boundary is undocumented | agents 4 vs 5, 2026-07-02 sweep | evidence for Q-A7 |

## 3. Named gaps (non-binding)

- `GUVNAH_DISPOSITION_UNRECORDED` — nothing in either repo says whether guvnah
  is alive. Whatever Q-A7 rules, the ruling gets written down in both.

## 4. Slices

All build slices **blocked on Q-A7** (reconciliation DECISIONS.md; recommendation:
defer to the UI-shell family verdict, C2). On a revive ruling, the first slices
would be: re-pin to `>=2.8`, run the 123-test suite against the live daemon
(record real exit codes), then wire-or-gap the 16 deferred namespaces. On a
retire ruling: a supersession README pointing at the surviving shell, and PARKED
or graveyard placement with LINEAGE note.

## 5. Do-not-build

- Nothing — literally no guvnah work — before the disposition ruling. The pin
  break is *evidence*, not an emergency: nothing operational depends on guvnah
  today.

## 6. Operator questions

- **Q-A7** (reconciliation DECISIONS.md): revive / retire / defer-to-C2.
  Recommendation on file: defer to the family verdict.
