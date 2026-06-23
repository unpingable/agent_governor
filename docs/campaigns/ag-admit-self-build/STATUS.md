# Status — ag-admit self-build

As of 2026-06-23.

## Committed (on `main`)

```
8a76306  ag_admit: waiver-admission completeness via Model A + ci consumer edge (Slice 3/3b)
fb4322d  ag_admit: add governed step admission toy loop
```

- **unpushed:** yes — both commits are local; `origin/main..HEAD` == these 2 only. Push is
  the operator's call (standing no-push-during-work-hours rule; "push-worthy" ≠ "push now").
- **not squashed:** substrate (`fb4322d`) and real dogfood (`8a76306`) are deliberately separate.

## Test state

- Targeted ag-admit + waiver surfaces: **green** (see [REPLAY.md](REPLAY.md)).
- Full suite: **16051 passed, 62 skipped, 1 failed**.
- **Known red (not a regression):** `test_pyproject_version_matches_latest_git_tag`
  — pre-existing version/tag drift (`pyproject 2.8.1` vs tag `stage3b2-first-effect`).
  This work touched neither `pyproject.toml` nor tags.

## Expected clean-tree state

After checkout, `git status --short` is empty. The only expected untracked artifact is
`working/slice3_receipts/` — and only after running the dogfood (regenerable, not
committed). See [REPLAY.md](REPLAY.md) "regenerable vs dirty".

## Scope completed

- Slices 0–2: governed toy loop (refuse→repair→admit→execute→commit, receipt-reconstructable).
- Slice 3 + 3b: waiver-completeness packet — **all four acceptance criteria stand** (Model A;
  `ci_verify` consumer edge). `gate_receipt.py` untouched; no closed-enum change.
- `ForbiddenSurfaceGate`: semantic companion to `DiffPathScopeGate` (`src/governor/forbidden_surface_gate.py`,
  `tests/test_forbidden_surface_gate.py`). Path authority ≠ semantic authority now mechanized.
- `self-correction-within-scope`: repair harness (`src/governor/self_correction.py`,
  `tests/test_self_correction.py`). Worker proposes a repaired step from a failure receipt;
  harness validates ancestry/scope/intent ([D009](DECISIONS.md)) and re-admits through the
  same gates. **The D008 build ladder is complete.**

## Current next packet

No new mechanism queued — the build ladder is done. What follows is **operational**: run
the loop at reduced throttle (T2→T3) and optionally wire a real Codex `RepairProvider`
(named, not built). See [NEXT.md](NEXT.md).

## Cold-start discovery

Registered as protocol, not just convention: `docs/loop-protocol.md` §9 (AUDIT) directs a
cold start to inspect `.governor/campaigns/*.yaml` + `docs/campaigns/*/STATUS.md` and apply
ratified `DECISIONS.md` defaults by ID before asking the operator. Inert — discovery does
not make this campaign active or touch `loop.json` WIP state.

## Live boundary

Path authority is necessary but **not** semantic authority (Slice 3 specimen). The forbidden
surfaces a future change must not silently mutate are enumerated in [GRANTS.yaml](GRANTS.yaml).
