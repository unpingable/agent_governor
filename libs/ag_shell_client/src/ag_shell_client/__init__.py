# SPDX-License-Identifier: Apache-2.0
"""ag_shell_client — the governor daemon shell contract surface.

The de-triplicated protocol (socket path, Content-Length framing, JSON-RPC 2.0,
-32001 auth error) + typed models operator shells (maude, phosphor) rely on.
CI-tested in-repo against the daemon it speaks to, so the contract cannot drift
silently. This is AG's mouth — not a shell's guts (per the boundary law).
"""

from .models import (
    KNOWN_DECISION_KINDS,
    KNOWN_URGENCIES,
    DecisionItem,
    DecisionOption,
    decisions_from_response,
)
from .protocol import (
    AUTH_ERROR_CODE,
    DaemonAuthError,
    RPCError,
    default_socket_path,
    encode_message,
    make_request,
    parse_response,
    read_message,
)

__all__ = [
    "AUTH_ERROR_CODE",
    "DaemonAuthError",
    "DecisionItem",
    "DecisionOption",
    "KNOWN_DECISION_KINDS",
    "KNOWN_URGENCIES",
    "RPCError",
    "decisions_from_response",
    "default_socket_path",
    "encode_message",
    "make_request",
    "parse_response",
    "read_message",
]

__version__ = "0.1.0"
