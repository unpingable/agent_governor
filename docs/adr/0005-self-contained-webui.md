# 0005 — Self-Contained WebUI

## Status

Accepted

## Context

The governor needs a web interface for chat + governance visualization. The standard approach is a JavaScript framework (React, Vue, Svelte) with a build toolchain (npm, webpack/vite, TypeScript compiler). This introduces:

- Node.js as a runtime dependency
- npm install as a build step (with potential version conflicts)
- A separate dev server for hot-reload
- Source maps for debugging transpiled code
- Framework-specific testing infrastructure

The governor's deployment target is diverse: local development, Docker containers, remote servers, CI environments. Every build dependency is friction.

## Decision

The WebUI is a **single self-contained HTML file** with inline CSS and JavaScript. No build step. No npm. No framework.

```
src/webui/static/index.html    — Chat + governor sidebar (~2500 lines)
src/webui/static/dashboard.html — v2 governance dashboard (~380 lines)
```

FastAPI serves the HTML directly:

```python
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text()
```

Key patterns:
- CSS custom properties for theming (dark mode via `prefers-color-scheme`)
- Vanilla JavaScript in a single IIFE closure
- Direct DOM manipulation, no virtual DOM
- Polling (3s interval for governor status, 5s for dashboard summary) instead of WebSockets
- `localStorage` for session persistence with server write-through

## Consequences

- **Zero frontend dependencies.** No Node.js, no npm, no build step. `pip install -e .` and `uvicorn webui.adapter:app` serves everything.
- **Fully auditable.** View the entire UI by reading one file. No transpilation, no minification, no hidden code paths.
- **Trivial Docker deployment.** No multi-stage build for frontend assets. The Python image is sufficient.
- **No component reuse across projects.** The UI is not an npm package. This is acceptable — the governor UI is bespoke, not a component library.
- **No TypeScript.** All JavaScript is untyped. Runtime errors are caught by testing, not the compiler. The tradeoff is acceptable for the UI's complexity level.
- **Large single files.** `index.html` is ~2500 lines. This is manageable but approaches the limit of single-file ergonomics. The v2 dashboard is a separate file rather than extending index.html.
- **Polling over WebSockets.** Simpler (no reconnection logic, no state synchronization) but higher latency. Acceptable for governance status updates that change on human timescales, not millisecond timescales.

## Source

- `specs/ux/WEBUI_UX_SPEC.md` ("Serves a self-contained chat + governor panel at a single URL — no external frontend needed.")
