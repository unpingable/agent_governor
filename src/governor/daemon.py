"""
Governor Daemon — JSON-RPC 2.0 control plane over stdio or Unix socket.

The daemon is the judge, not the author. No LLM backend.
`commit.fix` accepts candidate text from the client — the daemon validates
and records, it doesn't generate.

Transport: Content-Length framing (same as MCP server), JSON-RPC 2.0.
Primary: stdio (Electron spawns daemon as child process).
Secondary: Unix socket ($XDG_RUNTIME_DIR/governor-<hash>.sock).
"""

import asyncio
import hashlib
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# =============================================================================
# JSON-RPC 2.0 error codes
# =============================================================================

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
GOVERNOR_ERROR = -32000

PROTOCOL_VERSION = "1.0"


# =============================================================================
# Content-Length framing (same pattern as mcp_server.py)
# =============================================================================


async def read_message(reader: asyncio.StreamReader) -> dict | None:
    """Read a Content-Length framed JSON-RPC message."""
    headers: dict[str, str] = {}
    while True:
        line = await reader.readline()
        if not line:
            return None  # EOF
        decoded = line.decode("utf-8")
        if decoded in ("\r\n", "\n"):
            break
        if ":" in decoded:
            key, _, value = decoded.partition(":")
            headers[key.strip()] = value.strip()

    content_length_str = headers.get("Content-Length")
    if content_length_str is None:
        return None

    content_length = int(content_length_str)
    body = await reader.readexactly(content_length)
    return json.loads(body.decode("utf-8"))


async def write_message(writer: asyncio.StreamWriter, msg: dict) -> None:
    """Write a Content-Length framed JSON-RPC message."""
    json_bytes = json.dumps(msg).encode("utf-8")
    header = f"Content-Length: {len(json_bytes)}\r\n\r\n".encode("utf-8")
    writer.write(header + json_bytes)
    await writer.drain()


# =============================================================================
# JSON-RPC 2.0 dispatcher
# =============================================================================

# Handler type: async function taking params dict, returning result dict
Handler = Callable[[dict[str, Any]], Awaitable[Any]]


class Dispatcher:
    """JSON-RPC 2.0 method dispatcher."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    async def dispatch(self, request: dict) -> dict | None:
        """Dispatch a JSON-RPC request. Returns response dict or None for notifications."""
        if not isinstance(request, dict):
            return _error_response(None, PARSE_ERROR, "Parse error")

        jsonrpc = request.get("jsonrpc")
        if jsonrpc != "2.0":
            return _error_response(
                request.get("id"), INVALID_REQUEST, "Invalid JSON-RPC version"
            )

        method = request.get("method")
        if not isinstance(method, str):
            return _error_response(
                request.get("id"), INVALID_REQUEST, "Missing or invalid method"
            )

        request_id = request.get("id")
        params = request.get("params", {})

        # Notifications (no id) don't get responses
        is_notification = "id" not in request

        handler = self._handlers.get(method)
        if handler is None:
            if is_notification:
                return None
            return _error_response(
                request_id, METHOD_NOT_FOUND, f"Method not found: {method}"
            )

        try:
            if not isinstance(params, dict):
                params = {}
            result = await handler(params)
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except TypeError as e:
            if is_notification:
                return None
            return _error_response(request_id, INVALID_PARAMS, str(e))
        except Exception as e:
            if is_notification:
                return None
            return _error_response(request_id, GOVERNOR_ERROR, str(e))


def _error_response(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


# =============================================================================
# DaemonState — lazy-initialized governor subsystems
# =============================================================================


class DaemonState:
    """Lazy wrapper around governor subsystems for daemon handlers."""

    def __init__(self, governor_dir: Path, mode: str = "general") -> None:
        self.governor_dir = governor_dir
        self.root = governor_dir.parent
        self.mode = mode
        self._session_store = None
        self._receipt_system = None
        self._scar_ledger = None
        self._violation_resolver = None

    @property
    def session_store(self):
        if self._session_store is None:
            from .session_continuity import SessionStore
            self._session_store = SessionStore(self.governor_dir / "sessions")
        return self._session_store

    @property
    def receipt_system(self):
        if self._receipt_system is None:
            from .gate_receipt import GateReceiptSystem
            self._receipt_system = GateReceiptSystem(self.governor_dir)
        return self._receipt_system

    @property
    def scar_ledger(self):
        if self._scar_ledger is None:
            from .scars import ScarLedger
            scar_path = self.governor_dir / "scars.json"
            if scar_path.exists():
                self._scar_ledger = ScarLedger.from_dict(
                    json.loads(scar_path.read_text())
                )
            else:
                self._scar_ledger = ScarLedger()
        return self._scar_ledger

    @property
    def violation_resolver(self):
        if self._violation_resolver is None:
            from .violation_resolver import ViolationResolver
            self._violation_resolver = ViolationResolver(
                self.governor_dir, mode=self.mode
            )
        return self._violation_resolver


# =============================================================================
# Handler registration — 21 RPC methods
# =============================================================================


def register_handlers(dispatcher: Dispatcher, state: DaemonState) -> None:
    """Register all daemon RPC handlers."""

    # --- Handshake ---

    async def governor_hello(params: dict) -> dict:
        initialized = state.governor_dir.exists()
        return {
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": {
                "fix_mode": "candidate_only",
                "sessions": True,
                "intent": True,
                "receipts": True,
                "scars": True,
                "commit": True,
            },
            "governor": {
                "context_id": state.governor_dir.name
                if state.governor_dir.name != ".governor"
                else "default",
                "mode": state.mode,
                "initialized": initialized,
            },
        }

    async def governor_now(params: dict) -> dict:
        try:
            from .viewmodel import build_viewmodel
            vm = build_viewmodel(state.governor_dir, state.root)
            d = vm.to_dict()

            # Derive pill + sentence from viewmodel (ported from gov-webui summaries)
            pill = "OK"
            sentence = "Governor is running."

            session = d.get("session")
            if session:
                mode = session.get("mode", "unknown")
                sentence = f"Mode: {mode}."
            stability = d.get("stability")
            if stability and stability.get("drift_alert"):
                pill = "DRIFT"
                sentence += f" Drift alert: {stability['drift_alert']}."

            regime = d.get("regime")
            regime_name = regime.get("current") if regime else None

            violations = d.get("violations", [])
            if violations:
                pill = "BLOCK"
                sentence = f"{len(violations)} violation(s) pending."

            result: dict[str, Any] = {"pill": pill, "sentence": sentence}
            if regime_name:
                result["regime"] = regime_name
            return result
        except Exception as e:
            return {"pill": "UNKNOWN", "sentence": str(e)}

    async def governor_status(params: dict) -> dict:
        try:
            from .viewmodel import build_viewmodel
            vm = build_viewmodel(state.governor_dir, state.root)
            d = vm.to_dict()
            session = d.get("session") or {}
            return {
                "mode": state.mode,
                "envelope": session.get("mode", "unknown"),
                "context_id": "default",
                "facts_count": len(d.get("claims", [])),
                "decisions_count": len(d.get("decisions", [])),
                "violations_count": len(d.get("violations", [])),
                "schema_version": d.get("schema_version", "v2"),
            }
        except Exception as e:
            return {"mode": state.mode, "envelope": "unknown", "error": str(e)}

    # --- Sessions ---

    async def sessions_list(params: dict) -> list:
        return state.session_store.list_sessions()

    async def sessions_create(params: dict) -> dict:
        title = params.get("title", "Untitled")
        capsule = state.session_store.create_session(name=title, mode=state.mode)
        return capsule.to_dict()

    async def sessions_delete(params: dict) -> dict:
        session_id = params.get("id")
        if not session_id:
            raise ValueError("Missing required param: id")
        result = state.session_store.delete_session(session_id)
        return {"success": result}

    async def sessions_get(params: dict) -> dict | None:
        session_id = params.get("id")
        if not session_id:
            raise ValueError("Missing required param: id")
        capsule = state.session_store.load_session(session_id)
        if capsule is None:
            return None
        return capsule.to_dict()

    # --- Intent ---

    async def intent_templates(params: dict) -> dict:
        from .intent_compiler import BUILTIN_TEMPLATES
        templates = [
            {"name": name, "description": tmpl.get("description", "")}
            for name, tmpl in BUILTIN_TEMPLATES.items()
        ]
        return {"templates": templates}

    async def intent_schema(params: dict) -> dict:
        from .intent_compiler import build_form_schema
        template_name = params.get("template_name")
        if not template_name:
            raise ValueError("Missing required param: template_name")
        schema = build_form_schema(template_name, state.mode)
        return schema.to_dict()

    async def intent_validate(params: dict) -> dict:
        from .intent_compiler import (
            IntentFormResponse,
            IntentFormSchema,
            validate_response,
        )
        schema_id = params.get("schema_id")
        values = params.get("values", {})
        if not schema_id:
            raise ValueError("Missing required param: schema_id")

        # Rebuild schema from template to validate against
        template_name = params.get("template_name", "session_start")
        from .intent_compiler import build_form_schema
        schema = build_form_schema(template_name, state.mode)

        response = IntentFormResponse(
            schema_id=schema.schema_id,
            values=values,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        errors = validate_response(response, schema)
        return {"valid": len(errors) == 0, "errors": errors}

    async def intent_compile(params: dict) -> dict:
        from .intent_compiler import (
            IntentFormResponse,
            build_form_schema,
            compile_intent,
        )
        schema_id = params.get("schema_id")
        values = params.get("values", {})
        if not schema_id:
            raise ValueError("Missing required param: schema_id")

        template_name = params.get("template_name", "session_start")
        schema = build_form_schema(template_name, state.mode)

        response = IntentFormResponse(
            schema_id=schema.schema_id,
            values=values,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        result = compile_intent(response, schema, governor_dir=state.governor_dir)
        return result.to_dict()

    async def intent_policy(params: dict) -> dict:
        from .intent_compiler import get_form_policy
        policy = get_form_policy(state.mode)
        return {"mode": state.mode, "policy": policy.value}

    # --- Receipts ---

    async def receipts_list(params: dict) -> list:
        gate = params.get("gate")
        verdict = params.get("verdict")
        limit = params.get("limit")
        if limit is not None:
            limit = int(limit)
        receipts = state.receipt_system.query(
            gate=gate, verdict=verdict, limit=limit
        )
        return [r.to_dict() for r in receipts]

    async def receipts_detail(params: dict) -> dict:
        receipt_id = params.get("receipt_id")
        if not receipt_id:
            raise ValueError("Missing required param: receipt_id")
        receipt = state.receipt_system.receipt_store.get_by_id(receipt_id)
        if receipt is None:
            raise ValueError(f"Receipt not found: {receipt_id}")
        evidence = state.receipt_system.evidence_for(receipt)
        return {
            "receipt": receipt.to_dict(),
            "evidence": evidence,
        }

    # --- Scars ---

    async def scars_list(params: dict) -> dict:
        ledger = state.scar_ledger
        scars = [s.to_dict() for s in ledger.get_active_scars()]
        shields = [s.to_dict() for s in ledger.get_active_shields()]
        metrics = ledger.get_metrics()
        stats = {
            "total_scars": metrics["total_scars"],
            "hard_scars": metrics["hard_scars"],
            "total_shields": metrics["total_shields"],
            "health": (
                "CONSTRAINED" if metrics["hard_scars"] > 0
                else "CAUTIOUS" if metrics["total_scars"] > 0
                else "NOMINAL"
            ),
        }
        return {"scars": scars, "shields": shields, "stats": stats}

    async def scars_history(params: dict) -> list:
        limit = params.get("limit", 50)
        if limit is not None:
            limit = int(limit)
        history = state.scar_ledger.get_failure_history(limit=limit)
        return [e.to_dict() for e in history]

    # --- Commit / Waive ---

    async def commit_pending(params: dict) -> dict | None:
        pending = state.violation_resolver.get_pending()
        if pending is None:
            return None
        return pending.to_dict()

    async def commit_fix(params: dict) -> dict:
        """Validate candidate text against anchors. No LLM generation."""
        corrected_text = params.get("corrected_text")
        if not corrected_text:
            raise ValueError("Missing required param: corrected_text")

        pending = state.violation_resolver.get_pending()
        if pending is None:
            return {
                "action": "fix",
                "success": False,
                "message": "No pending violation to fix.",
            }

        # Validate the candidate against continuity anchors
        try:
            from .continuity import AnchorRegistry, ContinuityChecker
            registry = AnchorRegistry(state.governor_dir)
            checker = ContinuityChecker(registry)
            violations = checker.check(corrected_text)

            if violations:
                descs = [v.description for v in violations]
                return {
                    "action": "fix",
                    "success": False,
                    "message": f"Candidate still violates {len(violations)} anchor(s): {'; '.join(descs)}",
                }
        except ImportError:
            pass  # continuity module not available, accept candidate

        # Candidate passes — resolve
        from .violation_resolver import ResolutionStatus
        pending.status = ResolutionStatus.FIXED
        state.violation_resolver._save_pending(pending)
        state.violation_resolver.clear_pending()

        return {
            "action": "fix",
            "success": True,
            "message": "Candidate accepted. Violation resolved.",
            "new_content": corrected_text,
        }

    async def commit_revise(params: dict) -> dict:
        pending = state.violation_resolver.get_pending()
        if pending is None:
            return {
                "action": "revise",
                "success": False,
                "message": "No pending violation to revise.",
            }
        new_anchor_text = params.get("new_anchor_text")
        result = state.violation_resolver.resolve_revise(
            pending, new_anchor_text=new_anchor_text
        )
        return result.to_dict()

    async def commit_proceed(params: dict) -> dict:
        pending = state.violation_resolver.get_pending()
        if pending is None:
            return {
                "action": "proceed",
                "success": False,
                "message": "No pending violation.",
            }
        reason = params.get("reason", "")
        scope = params.get("scope")
        expiry = params.get("expiry")
        result = state.violation_resolver.resolve_proceed(
            pending, scope=scope, expiry=expiry
        )
        return result.to_dict()

    async def commit_exceptions(params: dict) -> list:
        exceptions = state.violation_resolver.list_exceptions()
        return [e.to_dict() for e in exceptions]

    # --- Register all ---

    dispatcher.register("governor.hello", governor_hello)
    dispatcher.register("governor.now", governor_now)
    dispatcher.register("governor.status", governor_status)

    dispatcher.register("sessions.list", sessions_list)
    dispatcher.register("sessions.create", sessions_create)
    dispatcher.register("sessions.delete", sessions_delete)
    dispatcher.register("sessions.get", sessions_get)

    dispatcher.register("intent.templates", intent_templates)
    dispatcher.register("intent.schema", intent_schema)
    dispatcher.register("intent.validate", intent_validate)
    dispatcher.register("intent.compile", intent_compile)
    dispatcher.register("intent.policy", intent_policy)

    dispatcher.register("receipts.list", receipts_list)
    dispatcher.register("receipts.detail", receipts_detail)

    dispatcher.register("scars.list", scars_list)
    dispatcher.register("scars.history", scars_history)

    dispatcher.register("commit.pending", commit_pending)
    dispatcher.register("commit.fix", commit_fix)
    dispatcher.register("commit.revise", commit_revise)
    dispatcher.register("commit.proceed", commit_proceed)
    dispatcher.register("commit.exceptions", commit_exceptions)


# =============================================================================
# Server entry points
# =============================================================================


async def serve_stdio(state: DaemonState) -> None:
    """Serve JSON-RPC over stdin/stdout. Electron child process mode."""
    dispatcher = Dispatcher()
    register_handlers(dispatcher, state)

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    # Wrap stdout for async writing
    write_transport, write_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(
        write_transport, write_protocol, reader, loop
    )

    logger.info("Daemon serving on stdio")

    try:
        while True:
            msg = await read_message(reader)
            if msg is None:
                break  # EOF
            response = await dispatcher.dispatch(msg)
            if response is not None:
                await write_message(writer, response)
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        writer.close()
        logger.info("Daemon stdio connection closed")


async def serve_unix(socket_path: Path, state: DaemonState) -> None:
    """Serve JSON-RPC over Unix socket. Shared daemon mode."""
    dispatcher = Dispatcher()
    register_handlers(dispatcher, state)

    async def handle_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.info("Client connected: %s", peer)
        try:
            while True:
                msg = await read_message(reader)
                if msg is None:
                    break
                response = await dispatcher.dispatch(msg)
                if response is not None:
                    await write_message(writer, response)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info("Client disconnected: %s", peer)

    # Clean up stale socket
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    server = await asyncio.start_unix_server(handle_client, path=str(socket_path))
    logger.info("Daemon serving on %s", socket_path)

    # Handle graceful shutdown
    stop = asyncio.Event()

    def _signal_handler() -> None:
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await stop.wait()
    finally:
        server.close()
        await server.wait_closed()
        if socket_path.exists():
            socket_path.unlink()
        logger.info("Daemon stopped")


def default_socket_path(governor_dir: Path) -> Path:
    """Compute the default Unix socket path for a governor directory."""
    xdg = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    dir_hash = hashlib.sha256(str(governor_dir.resolve()).encode()).hexdigest()[:12]
    return Path(xdg) / f"governor-{dir_hash}.sock"


def run_daemon(
    governor_dir: Path,
    mode: str = "general",
    stdio: bool = False,
    socket_path: Path | None = None,
) -> None:
    """Entry point for `governor serve`."""
    state = DaemonState(governor_dir, mode=mode)

    if stdio:
        asyncio.run(serve_stdio(state))
    else:
        if socket_path is None:
            socket_path = default_socket_path(governor_dir)
        asyncio.run(serve_unix(socket_path, state))
