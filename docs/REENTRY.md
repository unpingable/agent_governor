# AG Re-entry State

> **Canonical re-entry ledger.** The authority for "where is the work" across `/clear`. Branches
> are an implementation detail; this file is the map. **Invariant: any branch create / merge /
> delete / supersede updates this file in the same or the immediately-following commit.** State
> custody, not branch hygiene.
>
> **Location caveat (read this):** this file currently lives on `docs/constellation-records`, NOT
> on `main` — so a clean `main` checkout will not see it. The always-loaded backstop is the memory
> file `memory/reentry_2026_06_24_parked_tracks.md` (AI-facing, survives `/clear`). For true
> stranger-discoverability this ledger wants to live on `main` (it is the *map*, not feature work)
> or become a Spine edition. Pending operator call (see the session note below).

Last updated: 2026-06-24

## Active branches

| Branch | Purpose | Tip | Status | Resume point | Push dependency |
|---|---|---|---|---|---|
| `feat/playbooks-gov-loop` | Governed playbooks — Track B (canonical) | `04b8e56` | Slices 0–2 green | **Slice 3** (Wicket consumes the 3 measurement digests as *evidence*, not authority) — **fresh review required** | none |
| `feat/transition-kernel-slice-1b` | Transition kernel Slice 1b — Track A | `f003519` | complete, unpushed | supervisor hot-path pickup (`supervisor.py:752/:433`) — **PARKED** | **Standing must push first** (`~/git/standing` `1e62ba9`, `f101c55`) |
| `docs/constellation-records` | Non-binding doctrine + gap records | (this branch) | filed records | no build action | none |

`main` (`b4e76b6`) is clean and is **not** the source of truth for in-flight work.

## Subsumed / deleted branches

| Branch | Disposition |
|---|---|
| `docs/governed-playbooks-capture` | deleted — was merged into `feat/playbooks-gov-loop` |
| `feat/playbooks-slice-0` | deleted — was merged into `feat/playbooks-gov-loop` |
| `docs/borrow-ledger` | folded into `docs/constellation-records` |
| `docs/gap-observation-contracts` | renamed → `docs/constellation-records` |

(`backport/maude-excision`, `dev` are pre-existing, not from this session.)

## What's on `docs/constellation-records`

- `docs/doctrine/borrow-ledger.md` — convergent admissibility prior art (descriptive, non-binding).
- `specs/gaps/GOV_GAP_OBSERVATION_CONTRACTS_001.md` — human-authored observation contracts
  (candidate; primary build home is NQ; it's the governed-playbooks four-layer model at the
  witness seam).

## Stop lines

- **Do NOT start playbooks Slice 3** (Wicket-as-evidence) without fresh review — first
  runtime-adjacent seam; reserved.
- **Do NOT pick up the supervisor hot path** without an actual live need / blocker / regression
  (no forcing case yet).
- **Doc/gap records are NOT build authorization** — they reserve shape, nothing more.

## Re-enter a lane

```
git checkout feat/playbooks-gov-loop      # Track B — read docs/campaigns/governed-playbooks-track-b/CAMPAIGN.md
git checkout feat/transition-kernel-slice-1b   # Track A — read docs/campaigns/transition-kernel-pickup/STATUS.md
git checkout docs/constellation-records   # records — read the two files above
```

Note: `.governor/loop.json` is **STALE** (it tracks the completed AG-on-AG thread). Use *this*
ledger + the campaign cards, not loop.json.
