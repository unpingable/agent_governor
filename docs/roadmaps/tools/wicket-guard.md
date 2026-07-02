# Roadmap — wicket-guard × AG

**Status:** DRAFT (2026-07-02)
Repo: `~/git/wicket-guard` (HEAD `ea58946`, 2026-05-13, v0.0.1 — single commit,
pre-alpha) · Docket: governor-atlas has no case yet (correctly — no AG edge exists)

## 1. Contract snapshot — what AG assumes today

Nothing. AG has no import, client, or doc dependency on wicket-guard. It is a
diff→Intent cook (unified diff → wicket `check`) whose v0 covers exactly one
authority-bearing surface: identity-attribution mutations to LICENSE. Correctly
scoped as **preflight, not gate** — runs before merge, outside the governor path.

## 2. Observed drift (dated)

None — there is no contract to drift from. Staleness (one commit, 7 weeks) is
expected for a founding-regression skeleton.

## 3. Named gaps (non-binding)

- `WICKET_GUARD_SURFACE_SET` — the authority-bearing file set (LICENSE, NOTICE,
  CODEOWNERS, SECURITY.md) is named in its README but only LICENSE is covered.
  Wicket-guard's own gap, recorded here for the docket.

## 4. Slices

None in AG. First AG-side slice becomes possible only after wicket-guard covers
its named surface set and AG has a governed PR/merge flow to preflight (which is
also dossier's revive trigger — see PARKED.md; the two may be one forcing case).

## 5. Do-not-build

- No AG integration while pre-alpha (one founding regression is not a contract).
- No duplicating its cook inside AG — if AG needs diff-preflight, it calls
  wicket-guard; it does not grow a second one.

## 6. Operator questions

- Consolidation candidate #2 (CONSOLIDATION.md): does the diff-cook earn a
  separate repo, or fold into wicket until it grows? Adjudicated by C2, ruled by
  operator. No AG work is blocked either way.
