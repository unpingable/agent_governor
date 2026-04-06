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
    ) -> SessionRecord:
        """Create a new supervised session (does not launch yet)."""
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
        )

        events_path = self._state_dir / f"{session_id}_events.jsonl"
        bus = EventBus(session_id, events_path)

        from governor.runtime.budget import RunBudgetLedger, default_budget_policy

        facet = RuntimeFacet()
        facet.budget_policy = policy_context.get("budget_policy") if policy_context else None
        if facet.budget_policy is None:
            facet.budget_policy = default_budget_policy()
        facet.budget_ledger = RunBudgetLedger(
            session_id=session_id,
            policy_id=facet.budget_policy.policy_id if facet.budget_policy else "",
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

        self._transition(record, SessionStatus.LAUNCHING)
        bus.emit(EventKind.SESSION_LAUNCHING, SourceLayer.SUPERVISOR, record.backend_kind)

        try:
            config = LaunchConfig(
                session_id=session_id,
                cwd=record.cwd,
                task=record.task,
                operator_mode=record.operator_mode,
                policy_context=record.policy_context,
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

        promotion = detect_workspace_changes(record.cwd)
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
            revert_workspace,
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
                    "reason": reason,
                },
            )
        else:
            reject_promotion(promotion, reason)
            reverted = revert_workspace(record.cwd)
            bus.emit(
                EventKind.PROMOTION_RESOLVED,
                SourceLayer.OPERATOR,
                record.backend_kind,
                payload={
                    "promotion_id": promotion.promotion_id,
                    "decision": "rejected",
                    "changed_files": promotion.changed_files,
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
