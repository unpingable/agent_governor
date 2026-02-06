# History Boundary

## Before v1.0.0 (Formation Period)

- Exploratory commits, rapid iteration
- No squash policy, no branch discipline
- Single-branch development on `main`
- Provenance preserved as-is -- these commits are the formation record
- Dead-ends, half-thoughts, and scar tissue are visible and intentional

This is how systems get discovered. The messy history is honest history.

## After v1.0.0 (Governed Period)

- Branch-based workflow (`dev` + `feature/*` + `fix/*`)
- `main` always releasable, tagged versions only
- Feature branches for experiments
- Curated merges with meaningful commit messages
- CI must pass before landing on `main`

## Why this matters

Agent Governor says: contradictions persist, don't erase them. Receipts matter. Provenance is how you know what you know.

The git history *is* that. Rewriting history before v1.0.0 would violate the project's own invariants. The formation period stays as evidence. The governed period demonstrates the system working on itself.

Forward constraints, not retroactive cosmetic surgery.

## Boundary marker

```
v1.0.0  a82d0be  2026-02-05  Feature-complete governance engine
v1.0.1  21b8d1e  2026-02-06  Fix MCP safety deadlocks (CI hang)
```

Everything at or before `a82d0be` is formation period.
Everything after is governed period.
