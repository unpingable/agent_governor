# AG2 Dashboard UX Specification

## Version 0.1 — Governance Dashboard with Optional Chat

```yaml
status: gap
implemented: false
depends_on:
  - core/AG2_INSTRUMENT_SPEC.md
  - ux/WEBUI_UX_SPEC.md
  - profiles.py
  - continuity.py
  - telemetry.py
  - interferometry.py
blocking:
  - 2.0 WebUI deployment
  - Run-centric governance workflows
  - Reproducible execution
estimated_scope: large
```

### Companion to: AG2_INSTRUMENT_SPEC.md, WEBUI_UX_SPEC.md

---

## Executive Summary

The v1 WebUI is "chat with governance sidebar." The 2.0 surface inverts this: **governance dashboard with optional chat.** The primary objects are runs, claims, and receipts — not messages. The mental model is "local ML experiment tracker, but for receipts."

**Design Principle**: UI renders governance state. UI cannot override governance state. Profile is UX; anchors are law.

**Success Metric**: Operator can review a run's claims, violations, and evidence without reading the chat transcript.

---

## 1. Invariant Hierarchy (Non-Negotiable)

```
Kernel constraints (law)        — UI cannot disable
    |
Anchors (decisions)             — UI cannot touch
    |
Profile (UX preferences)       — UI can adjust
    |
UI controls (convenience)      — UI owns entirely
```

This hierarchy is enforced at the API layer, not by the UI. Even a compromised or buggy UI cannot:
- Disable kernel constraints
- Modify or delete anchors
- Bypass receipt requirements
- Suppress violation reporting

### Corollary Invariants

```yaml
D0_ui_cannot_override_anchors: Profile is UX, anchors are law. UI adjusts severity display, not enforcement.
D1_no_state_in_widgets: All state lives in artifacts (events.jsonl, claims.jsonl, manifest.json). UI is a view.
D2_stop_must_stop: Cancel request MUST terminate the run within timeout. No "cancel requested" limbo.
D3_no_interactive_stdin: UI produces a run plan (manifest). Execution never waits on interactive input.
D4_notebook_is_report: Post-hoc report generation consumes events.jsonl. Reports never drive execution.
```

---

## 2. Layout — Controls Left, Output Right

The layout externalizes the operator's mental model: **what I control** on the left, **what happened** on the right.

```
+---------------------------+----------------------------------------------+
|   CONTROLS (left)         |   OUTPUT (right)                             |
|                           |                                              |
|   Profile selector        |   Run list (filterable)                      |
|   Anchor summary (ro)     |     or                                       |
|   Backend selector        |   Run detail                                 |
|   Quick actions           |     - Timeline                               |
|     [ New Run ]           |     - Claims + evidence                      |
|     [ Compare ]           |     - Violations                             |
|     [ Rerun Last ]        |     - Repro block                            |
|                           |     or                                       |
|   Active run indicator    |   Artifact browser                           |
|     (progress + STOP)     |     or                                       |
|                           |   Chat (optional, collapsible)               |
|   Allowlist / filters     |                                              |
+---------------------------+----------------------------------------------+
|                    Status bar: regime | profile | last run verdict        |
+-------------------------------------------------------------------------|
```

### 2.1 Left Panel — Controls

The left panel contains everything the operator sets *before* or *during* a run. It is the input surface.

| Element | Behavior |
|---------|----------|
| Profile selector | Dropdown. Switches active profile. Cannot modify anchors. |
| Anchor summary | Read-only list. Shows active anchors with severity. Links to detail. |
| Backend selector | Dropdown. claude-code / codex / ollama. Runtime switch via `/v1/backends/switch`. |
| New Run | Opens run configuration: task description, profile, model, optional seed. |
| Compare | Opens interferometry comparison: select backends, enter prompt. |
| Rerun Last | One-click rerun of last run with same manifest (different `run_id`). |
| Active run | Shows progress bar + event count + elapsed time + **STOP** button. |
| Allowlist / filters | File path filters for run scope. |

### 2.2 Right Panel — Output

The right panel shows what happened. It is the output surface. Four views, tab-selectable:

**Runs** — Default view. Filterable list of runs.

```
Run #47  2026-02-06 14:32  claude-opus  strict    PASS  12 claims  0 violations
Run #46  2026-02-06 13:01  ollama:qwen  research  FAIL  8 claims   2 violations
Run #45  2026-02-06 11:15  codex        strict    PASS  15 claims  0 violations
```

**Detail** — Selected run expanded.

```
+-- Timeline ------------------------------------------+
| 14:32:01  prompt_sent          "Add auth middleware"  |
| 14:32:03  model_output         (1247 tokens)          |
| 14:32:04  tool_invocation      file_write src/auth.py |
| 14:32:04  file_write           receipt: sha256:ab12... |
| 14:32:05  tool_invocation      command_exec pytest    |
| 14:32:08  test_run             14 passed, 0 failed    |
| 14:32:08  policy_decision      PASS                   |
+------------------------------------------------------+

+-- Claims -------------------+-- Violations -----------+
| ASSERT file_changed         |  (none)                 |
|   src/auth.py  sha:ab12     |                         |
| ASSERT test_result           |                         |
|   pytest  14/14  sha:cd34   |                         |
| ASSERT invariant_satisfied  |                         |
|   no_secrets  sha:ef56      |                         |
+-----------------------------+-------------------------+

+-- Repro Block ------------------------------------------+
| ag2 replay run_47                                       |
| # or: ag2 run --manifest .agent_gov/runs/47/manifest.json |
+---------------------------------------------------------+
```

**Artifacts** — Content-addressed blob browser.

```
sha256:ab12...  src/auth.py       1.2KB  python
sha256:cd34...  pytest-output     3.4KB  text
sha256:ef56...  security-scan     0.8KB  json
```

**Chat** — Optional. Collapsible. For when the operator wants to talk to the model directly. Chat does not produce governance artifacts — runs do.

---

## 3. Run Manifest as UI Contract

The function signature IS the UI spec. `RUN_MANIFEST.json` defines what all clients render.

```python
@dataclass
class RunManifest:
    run_id: str                    # uuidv7
    created_at: datetime
    actor: Actor                   # human | agent | pipeline
    environment: Environment       # os, hostname, cwd, timezone
    repo: RepoState               # url, git_sha, dirty, branch
    config: RunConfig             # profile, anchors_hash, toolchain_versions
    inputs: RunInputs             # task_id, prompt_hash, seed
    models: list[ModelSpec]       # name, provider, version, parameters_hash
```

Any UI (web, CLI, VS Code, CI) renders the same manifest. No UI-specific state beyond layout preferences.

---

## 4. Controls Schema — `controls_schema.json`

The left panel is generated from a JSON Schema with render hints. This allows new controls to appear without UI code changes.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "profile": {
      "type": "string",
      "enum": ["greenfield", "established", "production", "hotfix", "refactor"],
      "default": "established",
      "x-render": "dropdown",
      "x-label": "Profile",
      "x-description": "Governance strictness preset. Cannot modify anchors."
    },
    "backend": {
      "type": "string",
      "enum": [],
      "x-render": "dropdown",
      "x-label": "Backend",
      "x-description": "Model backend for execution.",
      "x-dynamic": "/v1/backends"
    },
    "task": {
      "type": "string",
      "x-render": "textarea",
      "x-label": "Task",
      "x-description": "What to do. Becomes prompt_hash in manifest."
    },
    "scope": {
      "type": "array",
      "items": {"type": "string"},
      "x-render": "tag-input",
      "x-label": "File scope",
      "x-description": "Paths to include. Empty = entire repo."
    },
    "seed": {
      "type": "integer",
      "x-render": "number",
      "x-label": "Seed",
      "x-description": "Optional. For reproducible runs.",
      "x-advanced": true
    }
  },
  "x-actions": ["start", "cancel", "rerun", "compare"]
}
```

### Render Hint Vocabulary

| `x-render` | Widget |
|------------|--------|
| `dropdown` | Select menu. `x-dynamic` = fetch options from endpoint. |
| `textarea` | Multi-line text input. |
| `tag-input` | Chip/tag input for lists. |
| `number` | Numeric input with stepper. |
| `toggle` | Boolean switch. |
| `readonly` | Display only (for anchor summaries). |

### `x-advanced`

Controls marked `x-advanced: true` are hidden by default. Revealed by "Show advanced" toggle. Progressive disclosure without separate views.

---

## 5. UI Actions Contract

Four actions. Each has a defined API call, precondition, and feedback.

```python
@dataclass
class UIAction:
    name: str
    method: str            # HTTP method
    endpoint: str          # API path
    precondition: str      # When the button is enabled
    feedback: str          # What the UI shows on success

actions = [
    UIAction(
        name="start",
        method="POST",
        endpoint="/v2/runs",
        precondition="no active run",
        feedback="switch to run detail view, show progress",
    ),
    UIAction(
        name="cancel",
        method="POST",
        endpoint="/v2/runs/{run_id}/cancel",
        precondition="active run exists",
        feedback="STOP button turns to 'Cancelling...', then run shows CANCELLED verdict",
    ),
    UIAction(
        name="rerun",
        method="POST",
        endpoint="/v2/runs",   # body = last manifest with new run_id
        precondition="at least one completed run",
        feedback="new run starts, previous run remains in list",
    ),
    UIAction(
        name="compare",
        method="POST",
        endpoint="/v2/runs/compare",
        precondition="at least two backends configured",
        feedback="switch to comparison view (interferometry results)",
    ),
]
```

---

## 6. Streaming Protocol

Runs emit events in real time. The UI subscribes to a stream and renders incrementally.

### 6.1 Transport

SSE (Server-Sent Events) over HTTP. WebSocket is acceptable but SSE is preferred for simplicity and HTTP/2 compatibility.

```
GET /v2/runs/{run_id}/events?stream=true
Accept: text/event-stream

event: run_started
data: {"run_id": "...", "ts": "...", "manifest": {...}}

event: event
data: {"event_id": "...", "kind": "tool_invocation", "payload": {...}}

event: claim
data: {"claim_id": "...", "type": "test_result", "predicate": "passed", ...}

event: violation
data: {"finding_id": "...", "severity": "blocking", "summary": "..."}

event: run_completed
data: {"run_id": "...", "verdict": "PASS", "duration_ms": 12340}
```

### 6.2 Stable Event Types

```python
class StreamEventType(str, Enum):
    RUN_STARTED = "run_started"
    EVENT = "event"                  # wraps EventKind from AG2_INSTRUMENT_SPEC
    CLAIM = "claim"
    VIOLATION = "violation"
    PROGRESS = "progress"            # periodic: event_count, elapsed_ms, stage
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"
    RUN_FAILED = "run_failed"
    HEARTBEAT = "heartbeat"          # keepalive, every 15s
```

Clients MUST handle unknown event types by ignoring them (forward compatibility).

### 6.3 Reconnection

SSE `Last-Event-ID` header for reconnection. Server replays missed events from `events.jsonl`. Events are append-only so replay is safe.

---

## 7. STOP Must Stop

Cancellation is a first-class invariant, not a best-effort hint.

```yaml
cancel_contract:
  request: POST /v2/runs/{run_id}/cancel
  acknowledgement_timeout: 2s     # Server MUST acknowledge within 2s
  termination_timeout: 10s        # Run MUST terminate within 10s of acknowledgement
  outcome: RUN_CANCELLED event with partial results preserved

  # If termination_timeout expires:
  escalation: SIGKILL equivalent — process killed, run marked CANCELLED with
              cancellation_reason: "timeout_escalation"

  # Partial results:
  events_so_far: preserved in events.jsonl
  claims_so_far: preserved in claims.jsonl (marked scope=partial)
  receipts_so_far: preserved (content-addressed, always valid)
```

### UI Feedback

```
State 1: Active run     → STOP button (red)
State 2: Cancel sent    → "Cancelling..." (disabled, spinner)
State 3: Acknowledged   → "Stopping..." (disabled, progress drains)
State 4: Terminated     → Run shows CANCELLED verdict with partial claims
```

If State 2 persists > 2s without acknowledgement, show warning: "Cancel may not have been received. Force stop?"

---

## 8. Example Inputs as Templates

Known-good runs serve as one-click templates for reproducibility.

```python
@dataclass
class RunTemplate:
    name: str                      # human label
    description: str
    manifest_defaults: dict        # partial RunManifest fields
    example_task: str              # pre-filled task description
    expected_outcome: str          # "14 tests pass, no violations"
    last_successful_run_id: str | None
```

### Built-in Templates

| Template | Task | Profile | Purpose |
|----------|------|---------|---------|
| Smoke test | "Run pytest, report results" | strict | Verify setup works |
| Security scan | "Scan for vulnerabilities" | production | Baseline security |
| Interferometry | "Compare model outputs for {task}" | research | Cross-model comparison |
| Rerun last | *(from last manifest)* | *(from last manifest)* | Reproducibility check |

Templates appear as cards in the "New Run" dialog. Selecting a template pre-fills the controls. Operator can modify before starting.

---

## 9. Notebook as Report (Post Hoc)

Reports are generated from `events.jsonl` after a run completes. Reports never drive execution.

```python
class ReportGenerator(Protocol):
    def generate(self, run_id: str, events: list[Event], claims: list[AG2Claim]) -> Report: ...
```

### Report Sections

```
1. Run Summary
   - Manifest (environment, models, profile, git SHA)
   - Verdict: PASS / FAIL / CANCELLED
   - Duration, event count, claim count

2. Claims & Evidence
   - Table: claim type | subject | predicate | evidence refs
   - Expandable: click claim → shows linked receipts

3. Violations
   - Table: severity | rule | summary | resolution
   - Empty state: "No violations detected"

4. Timeline
   - Collapsed by default
   - Expandable: full event stream with timestamps

5. Reproducibility
   - Repro command block
   - Manifest hash for integrity verification
```

### Format

Reports are JSON (source of truth) + Markdown (human view). The markdown is a deterministic render of the JSON — never maintained separately.

---

## 10. Failure Modes to Avoid

| Anti-Pattern | Why It's Dangerous | Mitigation |
|-------------|-------------------|------------|
| State hidden in UI | Widget state is lost on refresh, not auditable | All state in artifacts. UI is a view. Invariant D1. |
| Interactive prompts without timeouts | UI hangs waiting for stdin | Manifest defines the run plan. No stdin. Invariant D3. |
| Demo UI mistaken for governance | Users think toggling a switch changes enforcement | Anchors are read-only in UI. Profile changes are labeled "display preference." Invariant D0. |
| Cancel that doesn't cancel | "Cancelling..." forever | Timeout escalation to forced termination. Invariant D2. |
| Chat as governance surface | Users type `governor approve` in chat | Chat is convenience. Runs are governance. Chat cannot produce receipts. |
| UI-specific endpoints | State only accessible through one client | All state via manifest/events/claims files. Any client can read. |

---

## 11. API Surface

### 11.1 Runs

```
POST   /v2/runs                         # Create and start a run
GET    /v2/runs                         # List runs (filterable: ?profile=&verdict=&since=)
GET    /v2/runs/{run_id}                # Run detail (manifest + verdict + stats)
GET    /v2/runs/{run_id}/events         # Events (JSONL or SSE stream)
GET    /v2/runs/{run_id}/claims         # Claims for this run
GET    /v2/runs/{run_id}/violations     # Violations for this run
GET    /v2/runs/{run_id}/report         # Generated report (JSON or Markdown via Accept header)
POST   /v2/runs/{run_id}/cancel         # Cancel active run
POST   /v2/runs/compare                 # Start interferometry comparison run
```

### 11.2 Artifacts

```
GET    /v2/artifacts/{hash}             # Retrieve content-addressed blob
GET    /v2/artifacts?run_id=&mime=       # List artifacts for a run
```

### 11.3 Controls

```
GET    /v2/controls/schema              # Controls schema (JSON Schema + render hints)
GET    /v2/controls/templates           # Available run templates
GET    /v2/profiles                     # Available profiles
GET    /v2/anchors                      # Active anchors (read-only)
GET    /v2/backends                     # Available backends
POST   /v2/backends/switch              # Switch active backend
```

### 11.4 Dashboard

```
GET    /v2/dashboard/summary            # Aggregate stats: total runs, pass rate, violation trends
GET    /v2/dashboard/regime             # Current regime state
```

---

## 12. Relationship to v1 WebUI

The v1 WebUI (`src/webui/adapter.py`) remains available at `/` for backward compatibility. The v2 dashboard is served at `/dashboard` (or replaces `/` when v2 is the default).

| v1 Surface | v2 Equivalent |
|-----------|--------------|
| Chat area (center) | Chat tab (right panel, collapsible) |
| Governor sidebar (left) | Controls panel (left) + runs/claims (right) |
| `/governor/status` polling | SSE event stream |
| `/governor/now` | Run detail timeline |
| Backend dropdown | Controls panel backend selector |
| Compare card | Interferometry comparison view |

v2 does not remove chat. It demotes it from primary surface to optional tab.

---

## 13. Acceptance Criteria

```yaml
v0_dashboard:
  - controls_schema.json served at /v2/controls/schema
  - Left panel renders from schema (profile, backend, task, scope)
  - Run list view with filters (profile, verdict, date)
  - Run detail view with timeline, claims, violations, repro block

v0_streaming:
  - SSE stream at /v2/runs/{run_id}/events
  - All StreamEventType values emitted
  - Reconnection via Last-Event-ID
  - Heartbeat every 15s

v0_cancel:
  - POST /v2/runs/{run_id}/cancel acknowledged within 2s
  - Run terminated within 10s
  - Partial results preserved
  - UI shows CANCELLED verdict

v0_templates:
  - At least 3 built-in templates
  - One-click rerun with previous manifest
  - Template pre-fills controls panel

v0_reports:
  - Report generated from events.jsonl post-run
  - JSON + Markdown output
  - No state created by report generation

v0_invariants:
  - UI cannot modify anchors (API rejects)
  - UI cannot disable kernel constraints (no endpoint exists)
  - All state survives browser refresh (read from artifacts)
  - Cancel within timeout or force-kill
```

---

## 14. Open Questions

1. **Session affinity**: Should the dashboard support multiple concurrent runs? Or one active run per session?
2. **Historical depth**: How far back does the run list go? Retention policy inherited from AG2 spec?
3. **Multi-user**: Does each user get their own run namespace, or are runs shared per project?
4. **Offline mode**: Should the dashboard work with pre-recorded runs (no live backend)?
5. **Chat integration depth**: Can chat *trigger* a run (e.g., "run tests"), or is it purely conversational?

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-06 | Initial gap spec. Controls-left/output-right, streaming, cancel contract, templates, report generation. |
