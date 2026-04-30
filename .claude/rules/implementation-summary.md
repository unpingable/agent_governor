# Implementation Summary

> Boot index. Pointers, not catalog.
>
> If you find yourself about to recite features here, stop — that belongs in `feature-history.md`. This file answers *"what do I need loaded before task classification?"*, not *"what has this project ever built?"*

## Where to look

| You need... | Read |
|-------------|------|
| Architecture rules, NLAI, common mistakes, claim/receipt types, envelopes | `CLAUDE.md` (always loaded) |
| Module paths, file layout, package structure | `.claude/rules/file-structure.md` (always loaded) |
| CLI commands and flags | `.claude/rules/cli-reference.md` (always loaded) |
| Feature names, design notes, history, supersession lineage | `.claude/rules/feature-history.md` (load on demand) |
| Test counts (snapshot) | `feature-history.md` Appendix; for live counts: `pytest --collect-only -q tests/ \| tail -1` |
| Active design questions, candidate primitives, gap specs | `specs/gaps/` |
| Per-domain governance rules | `.claude/rules/{fiction,nonfiction,ops}-governor.md` (path-scoped) |
| WebUI, writing modules, VS Code extension | `.claude/rules/{webui,writing-modules,vscode-extension}.md` |

## Anti-bloat tripwire

If you are about to add a `**Foo Module** — bullet list of capabilities` line to *this* file: don't. That belongs in `feature-history.md`. This file is intentionally a card catalog, not the library.
