# SPDX-License-Identifier: Apache-2.0
"""Runtime adapter protocol for supervised agent sessions.

Adapters are thin, backend-specific shims. They spawn runtimes,
observe events, accept control actions, and declare capabilities
honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class AdapterCapabilities:
    """Declared truth about what a backend supports.

    If a capability is False, the UI degrades honestly
    (shows "kill" not "pause", etc).
    """

    supports_pause: bool = False
    supports_resume: bool = False
    supports_native_tool_hooks: bool = False
    supports_structured_events: bool = False
    supports_input_injection: bool = False
    supports_graceful_shutdown: bool = False


@dataclass
class LaunchConfig:
    """Configuration for launching a backend runtime."""

    session_id: str
    cwd: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    operator_mode: str = "interactive"
    policy_context: dict[str, Any] = field(default_factory=dict)
    task: str | None = None


@dataclass
class BackendHandle:
    """Opaque handle to a running backend process."""

    pid: int | None = None
    native_session_ref: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NativeEvent:
    """Raw event from a backend, before normalization."""

    kind: str
    at: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ControlAction:
    """An action sent to the backend runtime."""

    kind: str  # pause | resume | approve | deny | kill | send_input
    target_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class RuntimeAdapter(Protocol):
    """Protocol for backend-specific runtime adapters.

    Adapters are thin. They should not become mini policy engines.
    """

    def launch(self, config: LaunchConfig) -> BackendHandle:
        """Spawn the backend runtime. Returns a handle."""
        ...

    def iter_events(self, handle: BackendHandle) -> Iterable[NativeEvent]:
        """Yield native events from the running backend.

        This may block. Callers should run in a thread or async wrapper.
        """
        ...

    def send_control(self, handle: BackendHandle, action: ControlAction) -> None:
        """Send a control action to the backend."""
        ...

    def shutdown(self, handle: BackendHandle, graceful: bool = True) -> None:
        """Terminate the backend. Graceful = SIGTERM + wait, else SIGKILL."""
        ...

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        """Map a native event to zero or more canonical event dicts.

        Returns dicts with keys matching CanonicalEvent fields
        (kind, source_layer, payload, tool_call_id, etc).
        The supervisor fills in session_id, seq, event_id.
        """
        ...

    def capabilities(self) -> AdapterCapabilities:
        """Declare what this backend supports. Truth, not aspiration."""
        ...

    def is_alive(self, handle: BackendHandle) -> bool:
        """Check if the backend process is still running."""
        ...
