# Contributing

## The One Rule

All development happens on feature branches. `main` is receipts.

## Branches

| Branch | Purpose | Broken allowed? |
|--------|---------|-----------------|
| `main` | Always releasable. Tagged versions only. | No. |
| `dev` | Integration. Where features land first. | Yes, but coherent. |
| `feature/*` | One idea, one branch. Short-lived. | Yes. |
| `fix/*` | Targeted repairs against `main` or `dev`. | Yes. |

No `release/*`, no `hotfix/*` unless actually needed.

## Workflow

1. Start from `dev`
2. Branch: `git checkout -b feature/your-thing`
3. Work freely. Commit often. Ugly commits are fine here.
4. When it coheres: merge back to `dev`
5. When `dev` is stable: merge to `main`, tag the release

## What goes where

- "Let me try something" -> branch first
- "This might work" -> branch first
- "I want to see what breaks" -> branch first
- "This is done and tested" -> `dev`, then `main`

## History policy

- No retroactive squashing of existing history
- Squash-on-merge to `main` is optional (prefer meaningful commit messages)
- Never rewrite published history
- Messy commits on feature branches are fine -- that's provenance

## Testing

```bash
python3 -m pytest tests/ -v    # Must pass before merging to dev
python3 -m pytest tests/ -v    # Must pass before merging to main
ruff check src/ tests/         # Must pass before merging to main
```

## Issue Standards

**Bug reports:** exact command, environment (OS + Python version + commit hash), expected vs actual, receipt ID or log snippet if applicable. Issues without reproduction steps may be closed.

**Feature requests:** concrete use case, not "wouldn't it be cool if." Check ROADMAP.md first — it may already be listed or explicitly not planned.

## What We Value

- Paper cuts (friction in actual use)
- Receipt/evidence chain failures (the invariants this project exists to enforce)
- Documentation gaps (things that confused you on first read)

## What We Don't Want

- Architecture astronautics ("you should rewrite this in Rust")
- Philosophical debates about alignment
- PRs that don't pass existing tests

## The meta-constraint

This project builds governance tooling. The repo is part of the argument. If the repo doesn't demonstrate governed development, that's a credibility gap.

See `docs/HISTORY_BOUNDARY.md` for the formation/governed period distinction.
