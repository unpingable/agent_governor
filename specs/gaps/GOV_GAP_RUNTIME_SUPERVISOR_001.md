# GOV_GAP_RUNTIME_SUPERVISOR_001

## Title
Agent Runtime Supervisor: Governed Session Abstraction for External Agent CLIs

## Status
Shipped in 2.8.0. Claude Code + Gemini CLI adapters, tool interception,
interventions, promotions, session forking, settings cleanup. Dogfood verified.
See `src/governor/runtime/` and `docs/SUPERVISED_MODE.md`.

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

**Supervised Session** — One governed attachment to one backend runtime. Two-part structure:
- **Capsule** (durable): extends `session_continuity.py`. Intent, constraints, authority, ledger, workspace state. Survives restart.
- **Runtime facet** (volatile): pid, adapter handle, attach state, live event sequence, intervention/promotion counts. Dies with the process.

Linked by `session_id`. Capsule is the continuity object. Runtime facet is the supervision state. Do not contaminate capsules with process-management sludge.

**Runtime Adapter** — Backend-specific shim. Thin. Declares capabilities honestly. First adapter: Claude Code (builds on `claude_hooks.py`).

**Canonical Event** — Normalized event from any backend. Sequenced per session, correlated to receipts.

**Intervention** — "Can this action proceed right now?" Blocking decision on a tool call or dangerous operation. Time-bounded. Lives in the intervention queue.

**Promotion** — "Do we accept this produced work?" Proposed side-effect or artifact requiring operator acknowledgment before it becomes adopted output. Lives in the promotion queue. Different queue, different semantics, different operator mood.

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

### Event Semantics

**Idempotency**: Events are identified by `(session_id, seq)`. If a hook fires twice for the same tool call (e.g., Claude retries), the adapter deduplicates by `tool_call_id` before assigning a new seq. Same native event → same canonical event, not a duplicate.

**Pairing**: `tool_call_proposed` and `tool_call_completed`/`tool_call_failed`/`tool_call_denied` are paired by `tool_call_id` in the payload, not by sequence adjacency. Multiple tool calls may be in flight (Claude Code can propose tools while previous ones complete).

**Restart**: On supervisor restart, the runtime facet is reconstructed from the adapter (is the child still alive?) and the persisted event index (last known seq). Events are NOT re-emitted. The event stream has a gap, which is recorded as a `supervisor_restart` event with the gap range.

**Maude reconnection**: Maude requests events from a `since_seq` cursor. The event store serves from persisted JSONL. No re-emission, no replay magic. If events were lost in the gap, the gap is visible.

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

Builds on existing `claude_hooks.py`. Two operating modes:

**Supervised mode** (Phase 0 target): Governor launches Claude Code as a managed child process. Governor owns the process lifecycle. This is the primary mode for Maude.

**Observer mode** (backward compat): Claude Code launches governor hooks as subprocesses (current behavior). Governor observes and intercepts but doesn't own the process. Useful for existing `governor hook` workflows.

Phase 0 implements supervised mode only. Observer mode continues to work via existing `claude_hooks.py` — no changes needed. Same adapter family, but different operational paths. Do not try to make one code path gracefully handle both modes.

Supervised mode details:

- **Launch**: spawn `claude` CLI with `--hooks-config` pointing to governor hook scripts (already implemented in `claude_hooks.py`)
- **Tool interception**: PreToolUse hook (already implemented) → `tool_call_proposed` event → policy decision → hook response (allow/deny)
- **Post-tool observation**: PostToolUse hook (already implemented) → `tool_call_completed` event
- **Task completion**: TaskCompleted hook (already implemented) → session lifecycle events
- **Structured events**: Claude Code emits JSON to hooks — `map_event` translates to canonical events
- **Capabilities**: `supports_native_tool_hooks=True`, `supports_structured_events=True`, `supports_pause=False` (soft pause only), `supports_graceful_shutdown=True`

The adapter is thin because the hook machinery already exists. The new work is:
1. Spawning Claude Code as a managed child process
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

### Workspace Change Detection

Change detection source of truth: **`git diff` against a known-clean baseline**, not filesystem watchers or write interception.

Rationale: filesystem watchers are racy and miss changes made by subprocesses of subprocesses. Write interception (wrapper.py) only catches governor-mediated writes. `git diff` is the single source of truth for "what actually changed in the worktree."

Detection trigger: **post-tool scan**. After each `tool_call_completed` that has write-capable tool class (bash, write, edit), the supervisor runs `git diff --name-only` against the session's baseline commit. New/changed files become workspace change events.

Baseline: set at session launch (current HEAD). Updated when promotions are approved (new baseline = post-promotion state).

### Timeout and Default Policy

Intervention timeouts are explicit and visible:

- **Default intervention timeout**: 300s (configurable per policy profile)
- **Default on timeout**: `deny` for write/execute/network tools, `allow` for read-only tools
- **Pause freezes timers**: if the operator pauses the session, intervention timers stop
- **UI shows countdown**: Maude displays time remaining on pending interventions
- **Timeout produces event**: `intervention_timeout` with the default action taken

Promotion timeouts: none by default. Promotions can sit pending indefinitely. Optional `promotion_expiry` per policy profile causes promotions to expire to `expired` status after N minutes of inactivity.

### Promotion Queue

A promotion is created when:
- Post-tool workspace scan detects file changes beyond the baseline
- Write action blocked for approval and operator needs to review the result
- Patch/diff produced by the agent
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

Promotions are the bridge from "agent chatter" to "real work product."

### Intervention vs Promotion

These are distinct queues with distinct semantics:

- **Intervention queue**: "Can this proceed?" Real-time gating of tool calls or dangerous operations. Time-bounded — if the operator doesn't respond within the timeout, the default policy applies (deny for dangerous ops, allow for safe ones). Interventions are about the *present action*.

- **Promotion queue**: "Do we accept this output?" Post-hoc review of produced work. Not time-bounded in the same way — promotions can sit pending until the operator reviews them. Promotions are about *accumulated results*.

An operator in intervention mode is a traffic cop. An operator in promotion mode is a code reviewer. Different cognitive state, different UI treatment.

### Intervention Outcomes: Approve / Deny / Edit-Resubmit

Phase 0 supports approve and deny. Phase 1 adds **edit-resubmit**: the operator modifies the proposed action before approving.

Edit-resubmit semantics:

- **Original proposal is immutable.** The `tool_call_proposed` event and its payload are never modified.
- **Operator edit produces a derived proposal.** New event `tool_call_edited` with `parent_event_id` pointing to the original proposal. The edited payload (e.g., modified bash command, changed file path) is the new subject.
- **Policy/invariant checks rerun on the edited artifact.** The derived proposal goes through the same gate as the original — no free pass for edits.
- **Execution resumes from the validated derived proposal.** The adapter receives the edited action, not the original.
- **Audit trail preserves lineage.** Receipt chain: original proposal → edit diff → derived proposal → policy re-evaluation → execution. The operator's modification is a first-class artifact with its own receipt.

New event kinds (Phase 1):
- `tool_call_edited` — operator modified the proposed action
- `tool_call_resubmitted` — edited action submitted for re-evaluation

New RPC (Phase 1):
- `runtime.intervention.edit` — modify and resubmit a pending intervention

This matters because binary approve/deny forces the operator into "accept the risk or kill the action." Edit-resubmit lets the operator say "almost, but change the path / drop the --force / add --dry-run." That's how real supervision works.

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

Two-part, matching the capsule/facet split:

**Capsule (durable, in session_continuity):**
- Session metadata (id, backend_kind, cwd, policy context)
- Intent, constraints, authority
- Promotion history (approved/rejected)
- Receipt linkage root

**Event store (append-only JSONL, per session):**
- Canonical events, rotated like signal store
- Enough to serve `since_seq` queries for Maude reconnection
- NOT the full agent transcript — events + receipts are the audit trail

**Runtime facet (volatile, in-memory):**
- pid, adapter handle, attach state
- Pending intervention queue
- Pending promotion queue
- Live event sequence counter
- Reconstructed from adapter + event store on restart

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
- `session_continuity.py` — capsule gains supervisor-related metadata fields (backend_kind, policy_context, promotion_history). Runtime facet is separate, NOT added to capsule.

## Open Questions

1. **Soft vs hard pause**: Start with soft pause (block tool approvals, hold input). Hard pause (SIGSTOP) is adapter-capability-dependent and probably not worth the complexity in Phase 0.

2. **Promotion granularity**: Per-file? Per-changeset? Per-task? Start with per-changeset (all files changed since last promotion checkpoint). Refine based on actual usage.

3. **Event retention**: How long do canonical events persist? They're lightweight but accumulate. Probably: keep recent N events in memory, persist to JSONL with rotation (like existing signal store pattern).

4. **Multi-session**: Phase 0 is one session. Multi-session (multiple agents working in different worktrees on the same repo) is Phase 2+ and maps to existing multi-agent dispatcher protocol.

5. **Git availability**: Workspace change detection assumes git. For non-git workspaces, fall back to file modification time scanning (less reliable, explicitly degraded). Declare this in adapter capabilities.

## Canonical Operator Surfaces (non-normative)

These are the default information architecture for Maude, not backend protocol. Runtime concepts should map cleanly to these zones.

| Pane | What it shows | Primary data source |
|------|--------------|-------------------|
| **Run Summary** | Current session state, lane/regime, risk level, next action, blocked/waiting status | Session record + runtime facet |
| **Timeline** | Checkpoints, state transitions, interrupts, commits. Diff between checkpoints. Which receipt justified each change. Fork/replay from any point. | Canonical event stream + session_continuity capsules |
| **Review Queue** | Pending interventions (with countdown) and promotions. Approve / deny / edit-resubmit. Clear "why you're being asked" context. | Intervention queue + promotion queue |
| **Receipts** | Evidence, policy matches, side-effect intents, receipt chains. What was checked, what passed, what failed. | Gate receipts + evidence store |
| **Topology** | Optional advanced view: subflows, nested agent runs, dependency graph. For debugging and postmortem, not daily driving. | Multi-agent dispatcher + execution graph |

Design principles:
- **Queue-first, not scroll-first.** The review queue is the primary interaction surface, not a raw event log.
- **Structured streaming, not token drizzle.** Progress updates are semantic ("evidence collection", "awaiting approval", "receipt committed"), not performative reasoning slurry.
- **Collapsible nesting.** Subflows and nested runs fold into the parent timeline. Expandable on demand.
- **Don't force the graph.** Topology pane is opt-in for power users. Default view is task/timeline/queue.

## Invariants

1. **Backend is not trusted.** The agent runtime is a supervised process. Its claims are proposals, not authority. (NLAI)
2. **Canonical events are authoritative for UI.** Maude renders canonical events, not backend-native strings.
3. **No invisible control actions.** Every operator action produces a canonical event.
4. **Adapter capabilities are declared truth.** If a capability isn't supported, the UI degrades honestly.
5. **Receipts link through.** Every policy decision during a supervised session produces a receipt traceable to the session and event that triggered it.
6. **Promotion is explicit.** Agent output becomes accepted work product only through the promotion queue, never by silent accumulation.
7. **Edits preserve lineage.** An operator edit produces a derived proposal with parent linkage, not a mutation of the original. Policy re-evaluates the edit.
