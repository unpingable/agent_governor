# SPDX-License-Identifier: Apache-2.0
"""Session supervisor for governed agent runtimes.

Manages the lifecycle of supervised sessions: launch, event normalization,
tool interception, operator intervention, and clean shutdown.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    LaunchConfig,
    RuntimeAdapter,
)
from governor.runtime.events import CanonicalEvent, EventBus, EventKind, SourceLayer


class InputInjectionError(Exception):
    """Operator input could not be delivered to a session.

    Fail-closed: raised when the backend does not declare
    ``supports_input_injection``, the session is not RUNNING, has no live
    handle, or the text is empty — rather than silently dropping the input."""


class SessionStatus(str, Enum):
    """Supervised session lifecycle states."""

    CREATED = "created"
    LAUNCHING = "launching"
    ATTACHING = "attaching"
    RUNNING = "running"
    WAITING_TOOL_DECISION = "waiting_tool_decision"
    WAITING_OPERATOR = "waiting_operator"
    PAUSED = "paused"
    DRAINING = "draining"
    EXITED = "exited"
    FAILED = "failed"


# Valid state transitions
_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.LAUNCHING, SessionStatus.FAILED},
    SessionStatus.LAUNCHING: {SessionStatus.ATTACHING, SessionStatus.FAILED},
    SessionStatus.ATTACHING: {SessionStatus.RUNNING, SessionStatus.FAILED},
    SessionStatus.RUNNING: {
        SessionStatus.WAITING_TOOL_DECISION,
        SessionStatus.WAITING_OPERATOR,
        SessionStatus.PAUSED,
        SessionStatus.DRAINING,
        SessionStatus.EXITED,
        SessionStatus.FAILED,
    },
    SessionStatus.WAITING_TOOL_DECISION: {
        SessionStatus.RUNNING,
        SessionStatus.WAITING_OPERATOR,
        SessionStatus.PAUSED,
        SessionStatus.DRAINING,
        SessionStatus.FAILED,
    },
    SessionStatus.WAITING_OPERATOR: {
        SessionStatus.RUNNING,
        SessionStatus.PAUSED,
        SessionStatus.DRAINING,
        SessionStatus.FAILED,
    },
    SessionStatus.PAUSED: {
        SessionStatus.RUNNING,
        SessionStatus.DRAINING,
        SessionStatus.FAILED,
    },
    SessionStatus.DRAINING: {SessionStatus.EXITED, SessionStatus.FAILED},
    SessionStatus.EXITED: set(),
    SessionStatus.FAILED: set(),
}


@dataclass
class Intervention:
    """A pending tool decision requiring operator action."""

    intervention_id: str
    tool_call_id: str
    tool_name: str
    tool_input: dict[str, Any]
    event_id: str  # The tool_call_proposed event
    created_at: float  # monotonic time
    timeout_seconds: float = 300.0
    resolved: bool = False
    decision: str | None = None  # "approve" | "deny"
    reason: str | None = None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def remaining(self) -> float:
        return max(0.0, self.timeout_seconds - self.elapsed)

    @property
    def timed_out(self) -> bool:
        return self.elapsed >= self.timeout_seconds


@dataclass
class RuntimeFacet:
    """Volatile runtime state for a supervised session.

    Dies with the process. Reconstructed on restart from adapter + event store.
    """

    handle: BackendHandle | None = None
    capabilities: AdapterCapabilities = field(default_factory=AdapterCapabilities)
    pending_interventions: dict[str, Intervention] = field(default_factory=dict)
    pending_promotion: Any = None  # Promotion | None (avoid circular import)
    budget_ledger: Any = None  # RunBudgetLedger | None (avoid circular import)
    budget_policy: Any = None  # BudgetPolicy | None
    lab_gate: Any = None  # LabGate | None (bootstrap_lab LA-backed effect gate)
    transition_probe: Any = None  # TransitionProbe | None (A2b: additive, flag-gated, default off)
    continuation_probe: Any = None  # ContinuationProbe | None (GAP-2 C2: observe/hold, no burn, default off)
    event_thread: threading.Thread | None = None
    running: bool = False


@dataclass
class SessionRecord:
    """Durable session metadata (capsule-adjacent)."""

    session_id: str
    backend_kind: str
    cwd: str
    status: SessionStatus
    operator_mode: str = "interactive"
    policy_context: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    updated_at: str = ""
    task: str | None = None
    pid: int | None = None
    exit_code: int | None = None
    parent_session_id: str | None = None
    # GAP-N (Tock 2): session-attributable promotion.
    allow_dirty: bool = False
    baseline_dirty: list[str] | None = None
    # NS-0 (nightshift-functional-mvp): extra argv appended to the backend
    # CLI at launch (e.g. ["--model", "claude-haiku-4-5"]). Operator-chosen
    # at create time; carries no authority — the gates don't care which
    # model proposes.
    harness_args: list[str] = field(default_factory=list)


def _new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


# ---------------------------------------------------------------------------
# Action classification: READ < WRITE < COMMUNICATE
# ---------------------------------------------------------------------------


class ActionClass(Enum):
    """Action class for tool calls. Higher = more scrutiny."""

    READ = "read"
    WRITE = "write"
    COMMUNICATE = "communicate"


# Static tool-name classification (case-insensitive lookup)
_TOOL_ACTION_CLASS: dict[str, ActionClass] = {
    # Claude Code — read
    "read": ActionClass.READ,
    "glob": ActionClass.READ,
    "grep": ActionClass.READ,
    # Claude Code — write
    "bash": ActionClass.WRITE,
    "write": ActionClass.WRITE,
    "edit": ActionClass.WRITE,
    "notebookedit": ActionClass.WRITE,
    # Gemini CLI — read
    "read_file": ActionClass.READ,
    "grep_search": ActionClass.READ,
    # Gemini CLI — write
    "replace": ActionClass.WRITE,
    "write_file": ActionClass.WRITE,
    "run_shell_command": ActionClass.WRITE,
}

# Patterns in Bash/shell commands that indicate communication
_COMMUNICATE_PATTERNS = (
    "curl ",
    "wget ",
    "gh pr ",
    "gh issue ",
    "git push",
    "git send-email",
    "slack ",
    "sendmail",
    "mail ",
    "smtp",
    "twilio",
    "notify-send",
    "osascript.*display notification",
)

# Legacy set for backward compat
_WRITE_TOOLS = {
    "bash", "write", "edit", "notebookedit",
    "Bash", "Write", "Edit", "NotebookEdit",
    "replace", "write_file", "run_shell_command",
}


def classify_action(tool_name: str, tool_input: dict[str, Any] | None = None) -> ActionClass:
    """Classify a tool call's action class.

    Static classification by tool name, with dynamic upgrade to COMMUNICATE
    for shell commands that target external communication endpoints.
    """
    base = _TOOL_ACTION_CLASS.get(tool_name.lower(), ActionClass.WRITE)

    # Dynamic upgrade: check shell command content for communication patterns
    if base == ActionClass.WRITE and tool_input:
        command = tool_input.get("command", "") or tool_input.get("cmd", "")
        if isinstance(command, str):
            cmd_lower = command.lower()
            for pattern in _COMMUNICATE_PATTERNS:
                if pattern in cmd_lower:
                    return ActionClass.COMMUNICATE

    return base


class SessionSupervisor:
    """Manages supervised agent sessions.

    Coordinates adapter lifecycle, event bus, and operator interventions.
    """

    def __init__(
        self,
        state_dir: Path | str,
        default_timeout: float = 300.0,
        on_event: Callable[[CanonicalEvent], None] | None = None,
    ) -> None:
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._default_timeout = default_timeout
        self._on_event = on_event  # Callback for real-time event delivery (e.g., to Maude)
        self._sessions: dict[str, SessionRecord] = {}
        self._facets: dict[str, RuntimeFacet] = {}
        self._buses: dict[str, EventBus] = {}
        self._adapters: dict[str, RuntimeAdapter] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        adapter: RuntimeAdapter,
        backend_kind: str,
        cwd: str,
        task: str | None = None,
        operator_mode: str = "interactive",
        policy_context: dict[str, Any] | None = None,
        allow_dirty: bool = False,
        harness_args: list[str] | None = None,
    ) -> SessionRecord:
        """Create a new supervised session (does not launch yet).

        ``allow_dirty=False`` (default) makes ``launch_session`` refuse a
        dirty working tree (GAP-N): without a clean start, session-attributable
        custody can't be established. ``allow_dirty=True`` instead records the
        pre-existing dirty set as a baseline and fences it from this session's
        promotion/rejection.
        """
        session_id = _new_session_id()
        now = _now_iso()

        record = SessionRecord(
            session_id=session_id,
            backend_kind=backend_kind,
            cwd=cwd,
            status=SessionStatus.CREATED,
            operator_mode=operator_mode,
            policy_context=policy_context or {},
            started_at=now,
            updated_at=now,
            task=task,
            allow_dirty=allow_dirty,
            harness_args=[str(a) for a in (harness_args or [])],
        )

        events_path = self._state_dir / f"{session_id}_events.jsonl"
        bus = EventBus(session_id, events_path)

        from governor.runtime.budget import RunBudgetLedger, default_budget_policy

        facet = RuntimeFacet()
        lab_cfg = (policy_context or {}).get("bootstrap_lab")
        if lab_cfg:
            # bootstrap_lab: LA is the SOLE spend authority on the effect path.
            # Deliberately do NOT stand up the BA3 budget ledger here, so no
            # internal budget competes with LA (acceptance §8). The action bound
            # is the LA grant, not an AG tunable — no ActiveTunableStore touched.
            from governor.runtime.lab_gate import LabGate

            gate = LabGate(
                la_client=lab_cfg["la_client"],
                session_id=session_id,
                actor=lab_cfg.get("actor", "inner_worker"),
                scope=lab_cfg.get("scope", f"lab/{session_id}"),
            )
            gate.acquire_grant(
                requested_capacity=lab_cfg.get("requested_capacity", 1),
                admission_receipt_id=lab_cfg.get("admission_receipt_id"),
                eligibility_valid_until=lab_cfg.get("eligibility_valid_until", 0),
                expires_after=lab_cfg.get("expires_after", 0),
                now=lab_cfg.get("now", 0),
            )
            facet.lab_gate = gate
            # Record the constellation edge: exactly which LA (version/commit/
            # binary) authorized this session's spend, pinned in the durable
            # event chain alongside the grant receipt.
            la_boundary = lab_cfg.get("la_boundary")
            if la_boundary:
                bus.emit(
                    "la_boundary",
                    SourceLayer.SUPERVISOR,
                    backend_kind,
                    payload={
                        **la_boundary,
                        "session_grant_scope": gate.scope,
                        "grant_receipt_id": gate.grant_receipt_id,
                    },
                )
        else:
            facet.budget_policy = (
                policy_context.get("budget_policy") if policy_context else None
            )
            if facet.budget_policy is None:
                facet.budget_policy = default_budget_policy()
            facet.budget_ledger = RunBudgetLedger(
                session_id=session_id,
                policy_id=facet.budget_policy.policy_id if facet.budget_policy else "",
            )

        # A2b: additive, flag-gated transition-kernel probe. Absent unless policy_context opts in, so
        # default behavior is byte-identical. Accepts a ready TransitionProbe or a config dict.
        probe_cfg = (policy_context or {}).get("transition_probe")
        if probe_cfg is not None:
            from governor.runtime.transition_subprocess import (
                TransitionProbe,
                TransitionSubprocess,
                default_office_context,
            )
            if isinstance(probe_cfg, TransitionProbe):
                facet.transition_probe = probe_cfg
            else:
                transport = probe_cfg.get("transport") or TransitionSubprocess(
                    binary_path=probe_cfg.get("binary_path")
                )
                if transport.identity is None:
                    transport.start()
                facet.transition_probe = TransitionProbe(
                    transport=transport,
                    mode=probe_cfg.get("mode", "observe"),
                    receipt_system=probe_cfg.get("receipt_system"),
                    build_office_context=probe_cfg.get("build_office_context")
                    or default_office_context,
                    memory_context_builder=probe_cfg.get("memory_context_builder"),
                )

        # GAP-2 C2: additive, flag-gated continuation probe (observe/hold; no burn). Absent unless
        # policy_context opts in. Accepts a ready ContinuationProbe or a config dict.
        cont_cfg = (policy_context or {}).get("continuation_probe")
        if cont_cfg is not None:
            from governor.runtime.transition_subprocess import (
                ContinuationProbe,
                TransitionSubprocess,
                default_next_step,
            )
            if isinstance(cont_cfg, ContinuationProbe):
                facet.continuation_probe = cont_cfg
            else:
                transport = cont_cfg.get("transport") or TransitionSubprocess(
                    binary_path=cont_cfg.get("binary_path")
                )
                if transport.identity is None:
                    transport.start()
                facet.continuation_probe = ContinuationProbe(
                    transport=transport,
                    mode=cont_cfg.get("mode", "observe"),
                    receipt_system=cont_cfg.get("receipt_system"),
                    prior_terminal=cont_cfg.get("prior_terminal", {}),
                    policy=cont_cfg.get("policy", {}),
                    next_step_builder=cont_cfg.get("next_step_builder") or default_next_step,
                    enforce_ledger_path=cont_cfg.get("enforce_ledger_path"),
                )

        with self._lock:
            self._sessions[session_id] = record
            self._facets[session_id] = facet
            self._buses[session_id] = bus
            self._adapters[session_id] = adapter

        bus.emit(
            EventKind.SESSION_CREATED,
            SourceLayer.SUPERVISOR,
            backend_kind,
            payload={"cwd": cwd, "task": task, "operator_mode": operator_mode},
        )

        return record

    def fork_session(
        self,
        parent_session_id: str,
        adapter: RuntimeAdapter,
        task: str | None = None,
    ) -> SessionRecord:
        """Fork a new session from a promoted prior session.

        The new session inherits the parent's workspace (cwd), backend kind,
        operator mode, and policy context. The workspace is in whatever state
        the parent left it (post-promotion). Parent linkage is explicit.

        The parent session must be exited with an approved promotion.
        """
        parent = self._get_record(parent_session_id)
        if parent.status != SessionStatus.EXITED:
            raise ValueError(f"Cannot fork from session in state {parent.status.value}")

        # Verify parent had an approved promotion
        parent_facet = self._facets.get(parent_session_id)
        if parent_facet and parent_facet.pending_promotion:
            p = parent_facet.pending_promotion
            if p.status != "approved":
                raise ValueError(f"Cannot fork from session with {p.status} promotion")

        record = self.create_session(
            adapter=adapter,
            backend_kind=parent.backend_kind,
            cwd=parent.cwd,
            task=task,
            operator_mode=parent.operator_mode,
            policy_context=parent.policy_context,
        )
        record.parent_session_id = parent_session_id

        # Emit fork event with parent linkage
        bus = self._get_bus(record.session_id)
        bus.emit(
            EventKind.SESSION_CREATED,  # Re-emit with parent info
            SourceLayer.SUPERVISOR,
            record.backend_kind,
            payload={
                "forked_from": parent_session_id,
                "parent_task": parent.task,
                "task": task,
            },
        )

        return record

    def launch_session(self, session_id: str) -> SessionRecord:
        """Launch the backend runtime for an existing session."""
        record = self._get_record(session_id)
        facet = self._get_facet(session_id)
        bus = self._get_bus(session_id)
        adapter = self._adapters[session_id]

        # GAP-N (Tock 2): snapshot the working-tree baseline BEFORE the backend
        # can touch anything. A dirty tree is refused by default; with
        # allow_dirty the pre-existing set is fenced from promote/reject.
        from governor.runtime.promotion import DirtyWorktreeError, snapshot_dirty_paths

        baseline = snapshot_dirty_paths(record.cwd)
        record.baseline_dirty = baseline
        if baseline and not record.allow_dirty:
            bus.emit(
                EventKind.SESSION_FAILED,
                SourceLayer.SUPERVISOR,
                record.backend_kind,
                payload={
                    "reason": "dirty_worktree_at_launch",
                    "preexisting_dirty": baseline,
                    "hint": "relaunch with allow_dirty=True to fence pre-existing changes",
                },
            )
            self._transition(record, SessionStatus.FAILED)
            raise DirtyWorktreeError(record.cwd, baseline)
        if baseline:
            bus.emit(
                EventKind.SESSION_LAUNCHING,
                SourceLayer.SUPERVISOR,
                record.backend_kind,
                payload={"baseline_dirty_fenced": baseline},
            )

        self._transition(record, SessionStatus.LAUNCHING)
        bus.emit(EventKind.SESSION_LAUNCHING, SourceLayer.SUPERVISOR, record.backend_kind)

        try:
            config = LaunchConfig(
                session_id=session_id,
                cwd=record.cwd,
                task=record.task,
                operator_mode=record.operator_mode,
                policy_context=record.policy_context,
                # NS-0: operator-chosen extra backend argv (e.g. --model).
                args=list(record.harness_args),
                # Thread the intervention decision window to the adapter so
                # backend-side gates (pre-tool hooks) wait at least as long
                # as the supervisor's timeout watcher before failing closed.
                env={"GOVERNOR_DECISION_TIMEOUT": str(self._default_timeout)},
            )
            handle = adapter.launch(config)
            facet.handle = handle
            facet.capabilities = adapter.capabilities()
            record.pid = handle.pid

            self._transition(record, SessionStatus.ATTACHING)
            bus.emit(EventKind.SESSION_ATTACHED, SourceLayer.SUPERVISOR, record.backend_kind,
                     payload={"pid": handle.pid})

            self._transition(record, SessionStatus.RUNNING)
            bus.emit(EventKind.SESSION_RUNNING, SourceLayer.SUPERVISOR, record.backend_kind)

            # Start event processing thread
            facet.running = True
            facet.event_thread = threading.Thread(
                target=self._event_loop,
                args=(session_id,),
                daemon=True,
                name=f"supervisor-{session_id[:8]}",
            )
            facet.event_thread.start()

        except Exception as e:
            self._transition(record, SessionStatus.FAILED)
            bus.emit(EventKind.SESSION_FAILED, SourceLayer.SUPERVISOR, record.backend_kind,
                     payload={"error": str(e)})

        return record

    def _event_loop(self, session_id: str) -> None:
        """Process events from the backend adapter."""
        facet = self._get_facet(session_id)
        record = self._get_record(session_id)
        bus = self._get_bus(session_id)
        adapter = self._adapters[session_id]

        if not facet.handle:
            return

        try:
            for native_event in adapter.iter_events(facet.handle):
                if not facet.running:
                    break

                canonical_dicts = adapter.map_event(native_event)
                for cd in canonical_dicts:
                    kind = cd.get("kind", "")
                    tool_call_id = cd.get("tool_call_id")

                    evt = bus.emit(
                        kind=kind,
                        source_layer=cd.get("source_layer", SourceLayer.ADAPTER),
                        backend_kind=record.backend_kind,
                        payload=cd.get("payload", {}),
                        tool_call_id=tool_call_id,
                    )

                    # Handle tool interception
                    if kind == EventKind.TOOL_CALL_PROPOSED:
                        self._handle_tool_proposed(session_id, evt, adapter)

                    # Record spend on tool completion
                    elif kind == EventKind.TOOL_CALL_COMPLETED:
                        self._record_step_spend(session_id, evt)

                    # Handle session exit
                    elif kind in (EventKind.SESSION_EXITED, EventKind.SESSION_FAILED):
                        if kind == EventKind.SESSION_EXITED:
                            self._transition(record, SessionStatus.EXITED)
                            record.exit_code = evt.payload.get("returncode")
                        else:
                            self._transition(record, SessionStatus.FAILED)

                        # Detect workspace changes → create promotion
                        self._detect_promotion(session_id)

                        # Emit budget ledger
                        if facet.budget_ledger:
                            bus.emit(
                                "budget_ledger",
                                SourceLayer.SUPERVISOR,
                                record.backend_kind,
                                payload=facet.budget_ledger.to_dict(),
                            )

                    # Deliver to callback (e.g., Maude)
                    if self._on_event:
                        try:
                            self._on_event(evt)
                        except Exception:
                            pass  # Callback errors must not break the event loop

        except Exception as e:
            bus.emit(EventKind.ADAPTER_ERROR, SourceLayer.SUPERVISOR, record.backend_kind,
                     payload={"error": str(e)})
            if record.status not in (SessionStatus.EXITED, SessionStatus.FAILED):
                self._transition(record, SessionStatus.FAILED)

        finally:
            facet.running = False

    def _handle_tool_proposed(
        self,
        session_id: str,
        event: CanonicalEvent,
        adapter: RuntimeAdapter,
    ) -> None:
        """Handle a tool call proposal — create intervention or auto-approve."""
        record = self._get_record(session_id)
        facet = self._get_facet(session_id)
        bus = self._get_bus(session_id)

        tool_name = event.payload.get("tool_name", "unknown")
        tool_call_id = event.payload.get("tool_call_id", "")

        # Check budget before allowing any tool call
        # Use spend + 1 tool call to catch the boundary correctly
        if facet.budget_policy and facet.budget_ledger:
            from governor.runtime.budget import Spend
            projected = facet.budget_ledger.total_spend + Spend(tool_calls=1)
            violation = facet.budget_policy.would_breach_hard(
                projected,
                facet.budget_ledger.total_steps + 1,
            )
            if violation:
                bus.emit(
                    EventKind.TOOL_CALL_DENIED,
                    SourceLayer.POLICY,
                    record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "reason": f"Budget exhausted: {violation.dimension} "
                                  f"({violation.actual}/{violation.limit})",
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="deny", target_id=tool_call_id,
                        payload={"reason": f"Budget exhausted: {violation.dimension}"},
                    ))
                return

        # Classify action: READ < WRITE < COMMUNICATE
        tool_input = event.payload.get("tool_input", {})
        action_class = classify_action(tool_name, tool_input)

        # GAP-2 C2: continuation gate (additive, flag-gated; default off → unchanged behavior). At the
        # next-step boundary, ask the kernel whether the agent earns ANOTHER governed step *before* the
        # per-effect transition gate. The previous effect being legitimate does not authorize the next
        # step. observe records the decision and lets the legacy loop continue (a non-grant is a LOUD
        # divergence — the old loop self-authorizes continuation); hold records and STOPS before the next
        # step. NO grant burn, no LA consume, no effect — that (present/burn) is C3, not here.
        cprobe = facet.continuation_probe
        # C3 enforce: a single-use continuation grant must be presented and durably BURNED before the next
        # step may reach the transition gate. No grant -> no next step; the legacy route is structurally
        # unreachable (this branch returns on every non-admit). The burn is the agent's next breath: it is
        # spent on the *attempt*, even if the downstream effect gate later refuses. Fail-closed, durable.
        if cprobe is not None and cprobe.mode == "enforce" and action_class == ActionClass.WRITE:
            cdec = cprobe.evaluate(tool_name=tool_name, tool_input=tool_input)
            if cdec is None or cdec.get("decision") != "grant":
                # No grant: fail-closed kernel, refusal, or escalation. Record durably (never fail-silent),
                # deny, and STOP — never fall through to legacy.
                reason = "fail_closed" if cdec is None else cdec.get("decision")
                detail = (cdec or {}).get("kind") or (cdec or {}).get("required_authority") or reason
                cprobe.record_refusal(grant_id=None, reason=f"continuation_{reason}:{detail}")
                bus.emit(
                    "continuation_denied", SourceLayer.POLICY, record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id, "tool_name": tool_name, "mode": "enforce",
                        "continuation_decision": reason, "detail": detail,
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="deny", target_id=tool_call_id,
                        payload={"reason": f"continuation enforce: {reason}"}))
                return
            # Grant issued — present and durably BURN it before the next step reaches the transition gate.
            grant = cdec["grant"]
            pres = cprobe.present(grant=grant, tool_name=tool_name, tool_input=tool_input)
            if pres.get("result") != "admitted":
                # Reused / expired / correspondence mismatch: the grant does not admit this step.
                cprobe.record_refusal(grant_id=grant.get("grant_id"),
                                      reason=f"continuation_present_refused:{pres.get('refusal')}")
                bus.emit(
                    "continuation_denied", SourceLayer.POLICY, record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id, "tool_name": tool_name, "mode": "enforce",
                        "continuation_decision": "present_refused", "detail": pres.get("refusal"),
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="deny", target_id=tool_call_id,
                        payload={"reason": f"continuation present refused: {pres.get('refusal')}"}))
                return
            # Burned. The next step reaches the transition gate; record that it did. A crash between the
            # burn and here leaves the grant spent_outcome_unknown (spent, not retryable).
            cprobe.finalize(grant["grant_id"])
            bus.emit(
                "continuation_admitted", SourceLayer.POLICY, record.backend_kind,
                payload={
                    "tool_call_id": tool_call_id, "tool_name": tool_name, "mode": "enforce",
                    "grant_id": grant["grant_id"],
                },
                tool_call_id=tool_call_id,
            )
            # Fall through to the unchanged transition/effect gate — the grant got the step *to* the gate,
            # not past it. The effect gate owns whether the effect happens.

        if cprobe is not None and cprobe.mode in ("observe", "hold") \
                and action_class == ActionClass.WRITE:
            cdec = cprobe.evaluate(tool_name=tool_name, tool_input=tool_input)
            granted = (cdec is not None) and (cdec.get("decision") == "grant")
            if cprobe.mode == "hold":
                # A hold stops before the next step regardless; a non-grant is additionally a divergence.
                if not granted:
                    cprobe.record_divergence(
                        decision=cdec, tool_name=tool_name, tool_call_id=tool_call_id,
                        governed_path="stopped_by_continuation_hold",
                    )
                bus.emit(
                    "continuation_held", SourceLayer.POLICY, record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id, "tool_name": tool_name, "mode": "hold",
                        "continuation_decision": (cdec or {}).get("decision", "fail_closed"),
                        "reason": "continuation hold: stop before next step (no burn, no consequence)",
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="deny", target_id=tool_call_id,
                        payload={"reason": "continuation hold (no consequence)"}))
                return
            # observe: the legacy loop continues below. A non-grant (refuse/escalate/fail-closed) while
            # the loop continues is exactly the AG-on-AG self-authorization we record loudly.
            if not granted:
                cprobe.record_divergence(
                    decision=cdec, tool_name=tool_name, tool_call_id=tool_call_id,
                    governed_path="continues",
                )
                bus.emit(
                    "continuation_divergence_observed", SourceLayer.POLICY, record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id, "tool_name": tool_name, "mode": "observe",
                        "continuation_decision": (cdec or {}).get("decision", "fail_closed"),
                        "classification": "kernel_refuse_continuation_vs_legacy_continue",
                    },
                    tool_call_id=tool_call_id,
                )
            # fall through to the unchanged path (transition probe / lab_gate / legacy)

        # A2b: transition-kernel probe (additive, flag-gated; default off → unchanged behavior).
        # Runs BEFORE the LA consume seam, on WRITE proposals only.
        #   observe → record the kernel decision; if the kernel would REFUSE while the governed path
        #             continues, emit a LOUD divergence receipt (never silently advisory), then fall
        #             through to the unchanged governed path.
        #   hold    → record the kernel decision, then STOP before any LA consume / effect. A hold, not
        #             an enforce: the candidate never mints authority here.
        probe = facet.transition_probe
        # 3b2 enforce: the full live consequence chain owns the decision. The legacy lab_gate route is
        # STRUCTURALLY UNREACHABLE from here — this branch always returns, so control never falls through
        # to the lab_gate block below. enforce never degrades into observe/legacy.
        if probe is not None and probe.mode == "enforce" and action_class == ActionClass.WRITE:
            res = probe.enforce(
                tool_name=tool_name, tool_input=tool_input, tool_call_id=tool_call_id,
            )
            succeeded = res.get("result") == "consumed_effect_succeeded"
            if succeeded:
                bus.emit(
                    EventKind.TOOL_CALL_ALLOWED, SourceLayer.POLICY, record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id, "tool_name": tool_name, "enforce": True,
                        "terminal": res["result"],
                        "consumption_event_id": res.get("consumption_event_id"),
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="approve", target_id=tool_call_id))
            else:
                # Refuse / Escalate / malformed / timeout / unavailable kernel-or-LA / failed
                # revalidation / failed correspondence / non-success terminal all block — fail-closed.
                bus.emit(
                    EventKind.TOOL_CALL_DENIED, SourceLayer.POLICY, record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id, "tool_name": tool_name, "enforce": True,
                        "terminal": res.get("result"), "reason": res.get("reason"),
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="deny", target_id=tool_call_id,
                        payload={"reason": f"enforce: {res.get('result')}"}))
            return

        if probe is not None and probe.mode in ("observe", "hold") and action_class == ActionClass.WRITE:
            probe_scope = getattr(facet.lab_gate, "scope", None) or "lab"
            kdec = probe.evaluate(
                tool_name=tool_name, tool_input=tool_input, scope=probe_scope, target=tool_name,
            )
            kernel_refused = (kdec is None) or (kdec.get("decision") != "admit")
            if probe.mode == "hold":
                if kernel_refused:
                    probe.record_divergence(
                        kernel_decision=kdec, tool_name=tool_name, tool_call_id=tool_call_id,
                        governed_path="stopped_by_hold",
                    )
                bus.emit(
                    "transition_probe_held",
                    SourceLayer.POLICY,
                    record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "mode": "hold",
                        "transition_decision": (kdec or {}).get("decision", "fail_closed"),
                        "reason": "transition_probe hold: stop before LA/effect (no consequence)",
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="deny", target_id=tool_call_id,
                        payload={"reason": "transition_probe hold (no consequence)"},
                    ))
                return
            # observe: the governed path will continue below. If the kernel refused, that is a
            # divergence we record loudly — we do not act on it (no enforce in A2b).
            if kernel_refused:
                probe.record_divergence(
                    kernel_decision=kdec, tool_name=tool_name, tool_call_id=tool_call_id,
                    governed_path="continues",
                )
                bus.emit(
                    "transition_divergence_observed",
                    SourceLayer.POLICY,
                    record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "mode": "observe",
                        "transition_decision": (kdec or {}).get("decision", "fail_closed"),
                        "classification": "kernel_refuse_vs_governed_continue",
                    },
                    tool_call_id=tool_call_id,
                )
            # fall through to the unchanged governed path

        # Bootstrap-lab LA-backed effect gate (the atlas spine made executable):
        # a WRITE effect crosses ONLY after LA authorizes consumption against the
        # session-scoped grant. The AG receipt/event witnesses the LA decision +
        # effect; it manufactures neither. Replay of a proposal → already_consumed;
        # exhausted grant → capacity_refused — both refuse BEFORE the effect.
        if facet.lab_gate is not None and action_class == ActionClass.WRITE:
            from governor.runtime.lab_gate import BOOTSTRAP_LAB_PROFILE

            # The gate owns its logical tick (LA's clock is caller-supplied; a
            # monotonic_ms tick would read as expired against the logical grant).
            decision = facet.lab_gate.decide_write_effect(tool_call_id=tool_call_id)
            if not decision.allowed:
                bus.emit(
                    EventKind.TOOL_CALL_DENIED,
                    SourceLayer.POLICY,
                    record.backend_kind,
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "profile": BOOTSTRAP_LAB_PROFILE,
                        "reason": f"LA refused effect: {decision.la_kind} ({decision.reason})",
                        "la_kind": decision.la_kind,
                        "consume_receipt_id": decision.consume_receipt_id,
                        "grant_receipt_id": facet.lab_gate.grant_receipt_id,
                        # Slice 2: worker-facing control fields so a denied worker
                        # knows whether retrying the same write can ever succeed.
                        "retry_disposition": decision.retry_disposition,
                        "terminal_scope": decision.terminal_scope,
                        "message": decision.message,
                    },
                    tool_call_id=tool_call_id,
                )
                if facet.handle:
                    adapter.send_control(facet.handle, ControlAction(
                        kind="deny", target_id=tool_call_id,
                        payload={
                            "reason": f"LA refused: {decision.la_kind}",
                            # The carrier actually delivered to the inner worker:
                            # an exhausted-grant denial says new authority is
                            # required, so the worker won't retry the same write.
                            "retry_disposition": decision.retry_disposition,
                            "terminal_scope": decision.terminal_scope,
                            "message": decision.message,
                        },
                    ))
                return
            # Consumed → the effect may cross. Bind the LA decision identity into
            # the effect event (acceptance §7: session · proposal · LA grant/consume · effect).
            bus.emit(
                EventKind.TOOL_CALL_ALLOWED,
                SourceLayer.POLICY,
                record.backend_kind,
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "action_class": action_class.value,
                    "profile": BOOTSTRAP_LAB_PROFILE,
                    "la_kind": "consumed",
                    "token_id": str(decision.token_id),
                    "consume_receipt_id": decision.consume_receipt_id,
                    "grant_receipt_id": facet.lab_gate.grant_receipt_id,
                    "remaining_capacity": decision.remaining_capacity,
                },
                tool_call_id=tool_call_id,
            )
            if facet.handle:
                adapter.send_control(facet.handle, ControlAction(
                    kind="approve", target_id=tool_call_id,
                ))
            return

        # In interactive mode, block write and communicate tools
        needs_approval = (
            record.operator_mode == "interactive"
            and action_class in (ActionClass.WRITE, ActionClass.COMMUNICATE)
        )

        if needs_approval:
            # Create intervention
            intervention = Intervention(
                intervention_id=f"int_{uuid.uuid4().hex[:8]}",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_input=tool_input,
                event_id=event.event_id,
                created_at=time.monotonic(),
                timeout_seconds=self._default_timeout,
            )
            facet.pending_interventions[tool_call_id] = intervention
            self._transition(record, SessionStatus.WAITING_TOOL_DECISION)

            payload: dict[str, Any] = {
                "intervention_id": intervention.intervention_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "action_class": action_class.value,
                "timeout_seconds": intervention.timeout_seconds,
            }
            # Communication gets extra visibility
            if action_class == ActionClass.COMMUNICATE:
                payload["communication_warning"] = True

            bus.emit(
                EventKind.OPERATOR_PROMPTED,
                SourceLayer.SUPERVISOR,
                record.backend_kind,
                payload=payload,
                tool_call_id=tool_call_id,
            )

            # Start timeout watcher
            threading.Thread(
                target=self._intervention_timeout_watcher,
                args=(session_id, tool_call_id),
                daemon=True,
            ).start()

        else:
            # Auto-approve read-only tools or in autonomous mode
            bus.emit(
                EventKind.TOOL_CALL_ALLOWED,
                SourceLayer.POLICY,
                record.backend_kind,
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "action_class": action_class.value,
                    "auto": True,
                },
                tool_call_id=tool_call_id,
            )
            if facet.handle:
                adapter.send_control(facet.handle, ControlAction(
                    kind="approve", target_id=tool_call_id,
                ))

    def _intervention_timeout_watcher(self, session_id: str, tool_call_id: str) -> None:
        """Watch for intervention timeout, apply default policy."""
        facet = self._get_facet(session_id)
        intervention = facet.pending_interventions.get(tool_call_id)
        if not intervention:
            return

        while not intervention.resolved and not intervention.timed_out:
            # Pause freezes timers
            record = self._get_record(session_id)
            if record.status == SessionStatus.PAUSED:
                time.sleep(0.5)
                continue
            time.sleep(0.5)

        if not intervention.resolved:
            # Timeout — deny write tools by default
            self.resolve_intervention(session_id, tool_call_id, "deny", reason="Intervention timeout")

    def resolve_intervention(
        self,
        session_id: str,
        tool_call_id: str,
        decision: str,
        reason: str | None = None,
    ) -> Intervention | None:
        """Resolve a pending intervention (approve/deny)."""
        facet = self._get_facet(session_id)
        record = self._get_record(session_id)
        bus = self._get_bus(session_id)
        adapter = self._adapters.get(session_id)

        intervention = facet.pending_interventions.get(tool_call_id)
        if not intervention or intervention.resolved:
            return None

        intervention.resolved = True
        intervention.decision = decision
        intervention.reason = reason

        if decision == "approve":
            bus.emit(
                EventKind.TOOL_CALL_ALLOWED,
                SourceLayer.OPERATOR,
                record.backend_kind,
                payload={"tool_call_id": tool_call_id, "tool_name": intervention.tool_name},
                tool_call_id=tool_call_id,
            )
            if adapter and facet.handle:
                adapter.send_control(facet.handle, ControlAction(
                    kind="approve", target_id=tool_call_id,
                ))
        else:
            bus.emit(
                EventKind.TOOL_CALL_DENIED,
                SourceLayer.OPERATOR,
                record.backend_kind,
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": intervention.tool_name,
                    "reason": reason or "Denied by operator",
                },
                tool_call_id=tool_call_id,
            )
            if adapter and facet.handle:
                adapter.send_control(facet.handle, ControlAction(
                    kind="deny", target_id=tool_call_id,
                    payload={"reason": reason or "Denied by operator"},
                ))

        bus.emit(
            EventKind.OPERATOR_DECISION,
            SourceLayer.OPERATOR,
            record.backend_kind,
            payload={
                "intervention_id": intervention.intervention_id,
                "tool_call_id": tool_call_id,
                "decision": decision,
                "reason": reason,
            },
        )

        # Remove from pending
        facet.pending_interventions.pop(tool_call_id, None)

        # Transition back to running if no more pending
        if not facet.pending_interventions and record.status == SessionStatus.WAITING_TOOL_DECISION:
            self._transition(record, SessionStatus.RUNNING)

        return intervention

    def _record_step_spend(self, session_id: str, evt: CanonicalEvent) -> None:
        """Record spend for a completed tool call."""
        from governor.runtime.budget import StepSpend, Spend

        facet = self._get_facet(session_id)
        record = self._get_record(session_id)
        bus = self._get_bus(session_id)

        if not facet.budget_ledger:
            return

        tool_name = evt.payload.get("tool_name", "unknown")
        step = StepSpend(
            step_index=facet.budget_ledger.total_steps,
            step_kind="tool",
            tool_name=tool_name,
            provider_kind="local",  # Claude Code tools are local
            spend=Spend(tool_calls=1),
        )
        facet.budget_ledger.record_step(step)

        # Check for budget violations after recording
        if facet.budget_policy:
            violation = facet.budget_policy.would_breach_hard(
                facet.budget_ledger.total_spend,
                facet.budget_ledger.total_steps,
            )
            if violation:
                facet.budget_ledger.violations.append(violation)
                bus.emit(
                    "budget_exhausted",
                    SourceLayer.SUPERVISOR,
                    record.backend_kind,
                    payload={
                        "dimension": violation.dimension,
                        "limit": violation.limit,
                        "actual": violation.actual,
                    },
                )

    def _detect_promotion(self, session_id: str) -> None:
        """Detect workspace changes at session end, create pending promotion."""
        from governor.runtime.promotion import detect_workspace_changes

        record = self._get_record(session_id)
        facet = self._get_facet(session_id)
        bus = self._get_bus(session_id)

        # GAP-N: scope the promotion to session-attributable changes by
        # excluding the launch-time baseline dirty set.
        promotion = detect_workspace_changes(record.cwd, baseline=record.baseline_dirty)
        if not promotion:
            return

        promotion.session_id = session_id
        facet.pending_promotion = promotion

        bus.emit(
            EventKind.PROMOTION_REQUIRED,
            SourceLayer.SUPERVISOR,
            record.backend_kind,
            payload={
                "promotion_id": promotion.promotion_id,
                "changed_files": promotion.changed_files,
                "excluded_files": promotion.excluded_files,
                "diff_stat": promotion.diff_stat,
            },
        )

        if self._on_event:
            # Also deliver via callback so Maude sees it
            pass  # Already delivered by the main emit path

    def resolve_promotion(
        self,
        session_id: str,
        decision: str,
        reason: str | None = None,
    ) -> "Promotion | None":
        """Resolve a pending promotion (approve/reject)."""
        from governor.runtime.promotion import (
            approve_promotion,
            reject_promotion,
            revert_paths,
        )

        facet = self._get_facet(session_id)
        record = self._get_record(session_id)
        bus = self._get_bus(session_id)

        promotion = facet.pending_promotion
        if not promotion or promotion.status != "pending":
            return None

        if decision == "approve":
            approve_promotion(promotion, reason)
            bus.emit(
                EventKind.PROMOTION_RESOLVED,
                SourceLayer.OPERATOR,
                record.backend_kind,
                payload={
                    "promotion_id": promotion.promotion_id,
                    "decision": "approved",
                    "changed_files": promotion.changed_files,
                    "excluded_files": promotion.excluded_files,
                    "reason": reason,
                },
            )
        else:
            reject_promotion(promotion, reason)
            # GAP-N: revert ONLY session-attributable paths. Pre-existing dirty
            # files (promotion.excluded_files) are never touched.
            reverted = revert_paths(record.cwd, promotion.changed_files)
            bus.emit(
                EventKind.PROMOTION_RESOLVED,
                SourceLayer.OPERATOR,
                record.backend_kind,
                payload={
                    "promotion_id": promotion.promotion_id,
                    "decision": "rejected",
                    "changed_files": promotion.changed_files,
                    "excluded_files": promotion.excluded_files,
                    "reason": reason,
                    "reverted": reverted,
                },
            )

        return promotion

    def get_budget(self, session_id: str) -> dict[str, Any] | None:
        """Get budget status for a session."""
        facet = self._facets.get(session_id)
        if not facet or not facet.budget_ledger:
            return None
        result = facet.budget_ledger.to_dict()
        if facet.budget_policy:
            result["policy"] = facet.budget_policy.to_dict()
            result["violations_current"] = [
                v.to_dict() for v in facet.budget_policy.check(
                    facet.budget_ledger.total_spend,
                    facet.budget_ledger.total_steps,
                )
            ]
        return result

    def get_pending_promotion(self, session_id: str) -> "Promotion | None":
        """Get the pending promotion for a session, if any."""
        facet = self._facets.get(session_id)
        if not facet:
            return None
        p = facet.pending_promotion
        if p and p.status == "pending":
            return p
        return None

    def pause_session(self, session_id: str) -> SessionRecord:
        """Soft pause: block tool approvals, freeze intervention timers."""
        record = self._get_record(session_id)
        bus = self._get_bus(session_id)
        self._transition(record, SessionStatus.PAUSED)
        bus.emit(EventKind.SESSION_PAUSED, SourceLayer.OPERATOR, record.backend_kind)
        return record

    def resume_session(self, session_id: str) -> SessionRecord:
        """Resume a paused session."""
        record = self._get_record(session_id)
        bus = self._get_bus(session_id)
        self._transition(record, SessionStatus.RUNNING)
        bus.emit(EventKind.SESSION_RESUMED, SourceLayer.OPERATOR, record.backend_kind)
        return record

    def send_input(self, session_id: str, text: str) -> SessionRecord:
        """Deliver operator text into a running session's backend (GS-5).

        Fail-closed at every gate: the backend must declare
        ``supports_input_injection``, the session must be RUNNING with a live
        handle, and the text must be a non-empty string. On success the input is
        sent via a ``send_input`` ControlAction and an OPERATOR_INPUT event is
        recorded on the bus (the audit trail of what the operator said). Raises
        :class:`InputInjectionError` on any unmet precondition — the input is
        never silently dropped.
        """
        if not isinstance(text, str) or not text.strip():
            raise InputInjectionError("input text must be a non-empty string")

        # Contract: "no such session" surfaces as InputInjectionError for every
        # caller, not a raw KeyError from the internal getters.
        try:
            record = self._get_record(session_id)
            facet = self._get_facet(session_id)
            bus = self._get_bus(session_id)
        except KeyError as exc:
            raise InputInjectionError(f"no such session: {session_id}") from exc
        adapter = self._adapters.get(session_id)

        if adapter is None or not facet.handle:
            raise InputInjectionError(f"session {session_id} has no live backend handle")
        if record.status != SessionStatus.RUNNING:
            raise InputInjectionError(
                f"session {session_id} is {record.status.value}, not running"
            )
        if not facet.capabilities.supports_input_injection:
            raise InputInjectionError(
                f"backend {record.backend_kind} does not support input injection"
            )

        # A backend that rejects the send is a delivery failure, surfaced
        # structurally — never a silent drop or an unhandled adapter exception.
        try:
            adapter.send_control(
                facet.handle,
                ControlAction(kind="send_input", payload={"text": text}),
            )
        except InputInjectionError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalize any adapter failure
            raise InputInjectionError(f"backend rejected input: {exc}") from exc
        bus.emit(
            EventKind.OPERATOR_INPUT,
            SourceLayer.OPERATOR,
            record.backend_kind,
            payload={"text": text, "chars": len(text)},
        )
        return record

    def kill_session(self, session_id: str) -> SessionRecord:
        """Kill a session (terminate backend process)."""
        record = self._get_record(session_id)
        facet = self._get_facet(session_id)
        bus = self._get_bus(session_id)
        adapter = self._adapters.get(session_id)

        facet.running = False

        if adapter and facet.handle:
            adapter.shutdown(facet.handle, graceful=False)

        # If already in terminal state, just return
        if record.status in (SessionStatus.EXITED, SessionStatus.FAILED):
            return record

        self._transition(record, SessionStatus.FAILED)
        bus.emit(EventKind.SESSION_FAILED, SourceLayer.OPERATOR, record.backend_kind,
                 payload={"reason": "Killed by operator"})
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Get session record by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[SessionRecord]:
        """List all sessions."""
        return list(self._sessions.values())

    def get_events(self, session_id: str, since_seq: int = 0, limit: int = 100) -> list[CanonicalEvent]:
        """Get canonical events for a session."""
        bus = self._buses.get(session_id)
        if not bus:
            return []
        return bus.since_seq(since_seq, limit)

    def get_pending_interventions(self, session_id: str) -> list[Intervention]:
        """Get pending interventions for a session."""
        facet = self._facets.get(session_id)
        if not facet:
            return []
        return [i for i in facet.pending_interventions.values() if not i.resolved]

    def _get_record(self, session_id: str) -> SessionRecord:
        record = self._sessions.get(session_id)
        if not record:
            raise KeyError(f"No session: {session_id}")
        return record

    def _get_facet(self, session_id: str) -> RuntimeFacet:
        facet = self._facets.get(session_id)
        if not facet:
            raise KeyError(f"No facet: {session_id}")
        return facet

    def _get_bus(self, session_id: str) -> EventBus:
        bus = self._buses.get(session_id)
        if not bus:
            raise KeyError(f"No event bus: {session_id}")
        return bus

    def _transition(self, record: SessionRecord, new_status: SessionStatus) -> None:
        """Transition session status, enforcing valid transitions."""
        old = record.status
        if new_status not in _TRANSITIONS.get(old, set()):
            # Allow no-op transitions (same state)
            if old == new_status:
                return
            raise ValueError(f"Invalid transition: {old} -> {new_status}")
        record.status = new_status
        record.updated_at = _now_iso()
