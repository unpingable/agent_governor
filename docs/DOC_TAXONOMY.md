# Document Taxonomy

## The Rule

**Could implementation be judged wrong by this document?**

- If yes → `specs/`
- If no → `docs/`

## specs/ — The Constitution

Normative, authoritative, design-contract documents.
What the system **is**, **must do**, or **still needs**.

```
specs/
  core/         # Shipped canonical specs (architecture, protocol, invariant)
  gaps/         # Explicit backlog — things we know are missing
  research/     # Non-committed lines of inquiry (not roadmap, not backlog)
```

## docs/ — The Field Manual

Explanatory, navigational, operational, user-facing material.
How to **understand**, **use**, **adopt**, or **work on** the system.

```
docs/
  architecture/ # Explanatory overviews, diagrams, import analysis
  adr/          # Architecture decision records (historical rationale)
  guides/       # Tutorials, workflows, user-facing how-tos
  reference/    # Command/tool/config reference material
  demo/         # Demo scripts and traces
  modes/        # Mode-specific operational docs
```

## Known Violations (cleanup backlog)

None outstanding. Resolved 2026-04-28:

- `docs/spec/PCAR-*` → `specs/core/`
- `specs/user/` → `docs/guides/`
- `specs/ux/` split: binding contracts (`AG2_DASHBOARD_UX_SPEC`, `AG2_WEBUI_DEMO_SPEC`) → `specs/core/`; design vision docs (`CLI_UX_SPEC`, `WEBUI_UX_SPEC`) → `docs/reference/`; `VSCODE_UX_SPEC` deleted (extension extracted to separate repo).

## What Lives Where (decision guide)

| Document type | Location | Example |
|---|---|---|
| Protocol spec | `specs/core/` | `ENTRAINMENT_CONTROL_MODEL.md` |
| Gap spec (known missing thing) | `specs/gaps/` | `GOV_GAP_COPILOT_ADAPTER_001.md` |
| Research note (speculative) | `specs/research/` | `TEMPORAL_CAPABILITY_KERNEL.md` |
| Architecture decision record | `docs/adr/` | `0001-proposal-commit-split.md` |
| User guide | `docs/guides/` | Code mode walkthrough |
| Architecture overview | `docs/architecture/` | Import diagrams |
| UX spec (binding contract) | `specs/core/` | Only if implementation can be wrong against it |
| UX guide (suggested layout) | `docs/reference/` | If it's guidance, not contract |
