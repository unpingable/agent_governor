---
paths:
  - "src/governor/check.py"
  - "src/governor/viewmodel.py"
  - "tests/test_check*"
  - "tests/test_viewmodel*"
  - "tests/test_state_cmd*"
---
# VS Code Extension (extracted to github.com/unpingable/vscode-governor)

## Architecture

- **esbuild** bundler (not webpack) — see `esbuild.mjs`
- CLI client wrapper spawns `governor` subprocess, parses JSON
- TypeScript types mirror Python CheckResult/CheckFinding/GovernorState
- TreeView uses GovernorViewModel schema v2 (8 sections)

## Python Support Modules

- **check.py** — Position, Range, CheckFinding, CheckResult, run_check (unified check aggregation)
- **viewmodel.py** — GovernorViewModel (schema v2), 8 section builders, read-only state derivation, V1 compat

## Extension Features (V1-V4)

- **V1**: CLI client, diagnostic provider, Check File/Check Selection commands, status bar, on-save handler
- **V2**: TreeView side panel, `governor state --json` aggregation, `--json` flags on 7 commands
- **V2-3**: GovernorViewModel canonical schema v2, TreeView rewrite with claim/decision/violation/evidence builders
- **V4**: Hover tooltips (GovernorHoverProvider), code actions (GovernorCodeActionProvider — quick fixes, suppress comments, security actions), real-time checking (RealtimeChecker — debounced on-type)

## Commands & Keybindings

- Check File: `Ctrl+Shift+G`
- Toggle Realtime: `Ctrl+Shift+Alt+G`
- Check Now, Show Output, Refresh State, Show Detail

**Total: 176 tests (87 Python + 89 TypeScript)**
