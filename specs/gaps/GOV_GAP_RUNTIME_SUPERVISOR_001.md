# GOV_GAP_RUNTIME_SUPERVISOR_001

## Title
Agent Runtime Supervisor: Governed Session Abstraction for External Agent CLIs

## Status
Gap spec (no code yet)

## Problem Statement

Governor has a daemon, a policy engine, receipt pipelines, hooks, session continuity, and autonomous execution machinery. What it does not have is a **supervisor layer that turns external agent runtimes into governed sessions with operator-facing control surfaces**.

The existing daemon (`governor serve`) is a policy/state engine. It answers "is this allowed?" and "what happened?" It does not answer "launch Claude Code in this worktree, watch what it does, let me approve tool calls, and show me the diffs when it's done."

The gap is the membrane between opaque agent subprocess and legible, interruptible, governed operator workflow.

## What Already Exists

These modules are substrate, not redundant:

| Module | What it provides | Relationship to supervisor |
|--------|-----------------|---------------------------|
| `claude_hooks.py` | PreToolUse/PostToolUse/TaskCompleted hooks for Claude CLI | **IS** the Claude Code adapter's interception mechanism. Phase 0 builds on this. |
| `session_continuity.py` | Capsule-based sessions, fork/promote, checkpoints, ledger persistence | Session model to extend, not replace. Supervisor adds runtime lifecycle on top. |
| `wrapper.py` | Agent wrapping with file write interception | Overlaps with tool boundary membrane. Supervisor subsumes this for managed sessions. |
| `execution.py` / `executor.py` | Budget tracking, checkpoint/resume, step-function loop | Autonomous execution substrate. Supervisor is the operator-facing layer above this. |
| `daemon.py` | JSON-RPC 2.0, 60+ methods, `chat.send`/`chat.stream`, backend auto-detection | RPC transport. Supervisor adds methods to this daemon, not a parallel one. |
| `evidence_gate.py` | Claim extraction, evidence linking, custody scoring | Policy decisions during tool interception feed through this. |
| `scope.py` | Locality-first policy, escalation receipts, tool contracts | Constrains where supervised agents can act. |

## What's New

1. **Canonical event bus** — Normalized event stream from backend-native sludge into uniform session events. This does not exist.
2. **Runtime adapter protocol** — Spawn/read/control/shutdown interface with declared capabilities per backend. This does not exist.
3. **Promotion queue** — First-class UX object for file changes, patches, artifacts requiring operator approval before acceptance. The concept exists in session_continuity (fork/promote) but not as an operator-facing queue.
4. **Observation/control plane split** — Explicit architectural boundary. Currently implicit.
5. **Operator intervention model** — Approve/deny/pause/resume/kill with timeout behavior and default policies. Partially exists in violation_resolver (fix/revise/proceed) but not for runtime supervision.

## Design

### Core Objects

**Supervised Session** — One governed attachment to one backend runtime. Extends `session_continuity.py` capsules with runtime lifecycle (pid, adapter, event stream, intervention queue).

**Runtime Adapter** — Backend-specific shim. Thin. Declares capabilities honestly. First adapter: Claude Code (builds on `claude_hooks.py`).

**Canonical Event** — Normalized event from any backend. Sequenced per session, correlated to receipts.

**Promotion** — Proposed side-effect requiring operator acknowledgment. Created by policy or supervisor observation.

### Session Lifecycle

```
created → launching → attaching → running ⇄ waiting_tool_decision
                                          ⇄ waiting_operator
                                          ⇄ paused
                                          → draining → exited
                                          → failed
```

States:
- **created**: session record exists, child not yet launched
- **launching**: adapter starting child process
- **attaching**: verifying hooks/streams/readiness
- **running**: normal execution
- **waiting_tool_decision**: blocked on policy/tool approval (maps to existing `claude_hooks.py` pre-tool flow)
- **waiting_operator**: blocked on explicit operator action
- **paused**: soft pause — no further tool approvals, input blocked
- **draining**: graceful shutdown
- **exited**: child exited normally
- **failed**: error terminated session

### Canonical Event Kinds

#### Lifecycle
- `session_created`, `session_launching`, `session_attached`, `session_running`
- `session_paused`, `session_resumed`, `session_draining`
- `session_exited`, `session_failed`

#### Tool boundary
- `tool_call_proposed` — adapter recognized a tool invocation attempt
- `tool_call_allowed` — policy permitted execution
- `tool_call_denied` — policy blocked execution
- `tool_call_completed` — tool executed and returned
- `tool_call_failed` — tool execution errored

#### Workspace
- `workspace_change_detected` — files changed in governed scope
- `promotion_required` — operator review needed
- `promotion_resolved` — operator approved/rejected

#### Operator
- `operator_prompted` — intervention needed
- `operator_decision` — operator acted

#### Faults
- `adapter_error`, `runtime_protocol_error`

#### Event envelope

```python
@dataclass(slots=True)
class CanonicalEvent:
    event_id: str
    session_id: str
    seq: int                          # monotonic per session
    at: str                           # ISO 8601
    kind: str                         # EventKind value
    source_layer: str                 # "adapter" | "supervisor" | "policy" | "operator"
    backend_kind: str
    correlation_id: str | None = None
    parent_event_id: str | None = None
    receipt_ids: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
```

### Adapter Contract

```python
class RuntimeAdapter(Protocol):
    def launch(self, config: LaunchConfig) -> BackendHandle: ...
    def iter_events(self, handle: BackendHandle) -> Iterable[NativeEvent]: ...
    def send_control(self, handle: BackendHandle, action: ControlAction) -> None: ...
    def shutdown(self, handle: BackendHandle, graceful: bool = True) -> None: ...
    def map_event(self, event: NativeEvent) -> list[CanonicalEvent]: ...
    def capabilities(self) -> AdapterCapabilities: ...
```

```python
@dataclass(frozen=True)
class AdapterCapabilities:
    supports_pause: bool
    supports_resume: bool
    supports_native_tool_hooks: bool    # Claude Code: yes. Generic subprocess: no.
    supports_structured_events: bool    # Claude Code: yes (JSON hooks). Raw CLI: no.
    supports_input_injection: bool      # Can we feed stdin to the agent?
    supports_graceful_shutdown: bool
```

Adapter capabilities are **declared truth, not aspirational**. If a backend doesn't support pause, the UI shows "kill" not "pause."

### Claude Code Adapter (Phase 0)

Builds on existing `claude_hooks.py`:

- **Launch**: spawn `claude` CLI with `--hooks-config` pointing to governor hook scripts (already implemented in `claude_hooks.py`)
- **Tool interception**: PreToolUse hook (already implemented) → `tool_call_proposed` event → policy decision → hook response (allow/deny)
- **Post-tool observation**: PostToolUse hook (already implemented) → `tool_call_completed` event
- **Task completion**: TaskCompleted hook (already implemented) → session lifecycle events
- **Structured events**: Claude Code emits JSON to hooks — `map_event` translates to canonical events
- **Capabilities**: `supports_native_tool_hooks=True`, `supports_structured_events=True`, `supports_pause=False` (soft pause only), `supports_graceful_shutdown=True`

The adapter is thin because the hook machinery already exists. The new work is:
1. Spawning Claude Code as a managed child process (vs current model where Claude Code spawns governor hooks)
2. Wrapping hook I/O into the canonical event bus
3. Managing the session lifecycle around the child process

### Observation vs Control Planes

**Observation (read-only):**
- Canonical event stream
- Tool proposals/results
- File changes
- Policy decisions
- Receipt linkage
- Diff availability

**Control (operator actions):**
- `pause` / `resume`
- `approve` / `deny` (tool calls and promotions)
- `kill`
- `detach` / `reattach`

Control actions produce events. Nothing happens invisibly.

### Promotion Queue

A promotion is created when:
- File changes cross threshold
- Write action blocked for approval
- Patch/diff produced
- Policy requires operator acceptance

```python
@dataclass
class Promotion:
    promotion_id: str
    session_id: str
    created_at: str
    status: str                   # pending | approved | rejected | superseded | expired
    subject_kind: str             # file_change | patch | artifact | git_action
    subject_refs: list[str]
    summary: str
    diff_available: bool
    risk_flags: list[str]
    receipt_ids: list[str]
```

Promotions are the bridge from "agent chatter" to "real work product." The operator approves promotions, not tool calls (though tool calls may also need approval for dangerous operations).

### Daemon RPC Extensions

New methods on existing `governor serve` daemon:

```
runtime.session.create      # create session record
runtime.session.launch      # spawn backend via adapter
runtime.session.list        # list sessions
runtime.session.get         # session detail
runtime.session.pause       # soft pause
runtime.session.resume      # resume
runtime.session.kill        # terminate
runtime.session.events      # query canonical events (with tail/poll)
runtime.intervention.list   # pending tool decisions
runtime.intervention.resolve # approve/deny
runtime.promotion.list      # pending promotions
runtime.promotion.resolve   # approve/reject
runtime.promotion.diff      # get diff for promotion
```

### Persistence

Extends existing session_continuity capsules:
- Session metadata + runtime state
- Canonical event index (enough to reconstruct recent state)
- Pending interventions/promotions
- Receipt linkage

Full transcript is NOT required for MVP. Events + receipts are the audit trail.

## Phase Plan

### Phase 0: One backend, happy path

- Claude Code adapter (builds on `claude_hooks.py`)
- Session lifecycle (created → running → exited)
- Canonical event bus
- Tool interception → approve/deny
- `runtime.*` RPC methods on daemon
- Basic Maude session pane (status, events, pending approvals)
- Receipt linkage

**Proves:** session abstraction, event normalization, tool membrane, operator intervention, receipt continuity.

### Phase 1: Promotions and workspace awareness

- File change detection in governed scope
- Promotion queue
- Diff inspection
- Approval annotations
- Session history replay

**Proves:** the thing produces reviewable work product, not just supervised chatter.

### Phase 2: Backend plurality

- Codex adapter
- Gemini CLI adapter
- Generic subprocess fallback (no structured events, stderr scraping only)
- Stress-test canonical event model against real backend diversity

**Proves:** the abstraction holds across backends, not just Claude Code.

## Module Plan

New:
- `src/governor/runtime/` — new package
  - `supervisor.py` — SessionSupervisor, manages session lifecycle
  - `events.py` — CanonicalEvent, EventKind, event bus
  - `adapter.py` — RuntimeAdapter protocol, AdapterCapabilities, LaunchConfig
  - `adapters/claude_code.py` — Claude Code adapter (wraps claude_hooks.py)
  - `promotion.py` — Promotion, PromotionQueue
  - `intervention.py` — InterventionQueue, operator decision model

Extended:
- `daemon.py` — add `runtime.*` RPC methods
- `session_continuity.py` — extend capsules with runtime lifecycle fields

## Open Questions

1. **Inversion of control**: Currently Claude Code launches governor hooks as subprocesses. The supervisor inverts this — governor launches Claude Code. Both models should work. The adapter needs to handle "I spawned you" and potentially "you spawned me" (for backward compat with existing hook-only setup).

2. **Soft vs hard pause**: Start with soft pause (block tool approvals, hold input). Hard pause (SIGSTOP) is adapter-capability-dependent and probably not worth the complexity in Phase 0.

3. **Promotion granularity**: Per-file? Per-changeset? Per-task? Start with per-changeset (all files changed since last promotion checkpoint). Refine based on actual usage.

4. **Event retention**: How long do canonical events persist? They're lightweight but accumulate. Probably: keep recent N events in memory, persist to JSONL with rotation (like existing signal store pattern).

5. **Multi-session**: Phase 0 is one session. Multi-session (multiple agents working in different worktrees on the same repo) is Phase 2+ and maps to existing multi-agent dispatcher protocol.

## Invariants

1. **Backend is not trusted.** The agent runtime is a supervised process. Its claims are proposals, not authority. (NLAI)
2. **Canonical events are authoritative for UI.** Maude renders canonical events, not backend-native strings.
3. **No invisible control actions.** Every operator action produces a canonical event.
4. **Adapter capabilities are declared truth.** If a capability isn't supported, the UI degrades honestly.
5. **Receipts link through.** Every policy decision during a supervised session produces a receipt traceable to the session and event that triggered it.
6. **Promotion is explicit.** Agent output becomes accepted work product only through the promotion queue, never by silent accumulation.
