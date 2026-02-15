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
import configparser
import hashlib
import json
import logging
import os
import shutil
import signal
import sys
import uuid
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
AUTH_ERROR = -32001

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

# Streaming handler: takes (params, notify_callback), returns final result
# The notify_callback sends JSON-RPC notifications to the client
NotifyFn = Callable[[str, dict[str, Any]], Awaitable[None]]
StreamingHandler = Callable[[dict[str, Any], NotifyFn], Awaitable[Any]]


class Dispatcher:
    """JSON-RPC 2.0 method dispatcher."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._streaming_handlers: dict[str, StreamingHandler] = {}

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    def register_streaming(self, method: str, handler: StreamingHandler) -> None:
        """Register a streaming handler that can send notifications during execution."""
        self._streaming_handlers[method] = handler

    async def dispatch(
        self,
        request: dict,
        writer: asyncio.StreamWriter | None = None,
    ) -> dict | None:
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

        # Check streaming handlers first
        streaming_handler = self._streaming_handlers.get(method)
        if streaming_handler is not None:
            try:
                if not isinstance(params, dict):
                    params = {}

                async def notify(notify_method: str, notify_params: dict[str, Any]) -> None:
                    """Send a JSON-RPC notification to the client."""
                    if writer is not None:
                        msg = {
                            "jsonrpc": "2.0",
                            "method": notify_method,
                            "params": notify_params,
                        }
                        await write_message(writer, msg)

                result = await streaming_handler(params, notify)
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
            # Surface auth errors with a specific code so clients can detect them
            from .chat_bridge import BackendAuthError
            if isinstance(e, BackendAuthError):
                return _error_response(request_id, AUTH_ERROR, str(e))
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


def load_daemon_config(governor_dir: Path) -> dict[str, str]:
    """Load daemon config from $GOVERNOR_DIR/daemon.conf if it exists.

    Returns a flat dict of key-value pairs. Env vars override config file.
    Config file is INI format with [backend] and [daemon] sections.
    """
    config_path = governor_dir / "daemon.conf"
    result: dict[str, str] = {}

    if config_path.exists():
        cp = configparser.ConfigParser()
        try:
            cp.read(str(config_path))
        except configparser.Error:
            logger.warning("Failed to parse %s", config_path)
            return result

        # Flatten sections into dot-separated keys
        for section in cp.sections():
            for key, value in cp.items(section):
                result[f"{section}.{key}"] = value

    return result


def detect_backend(
    config: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Auto-detect the best available backend from env vars and config.

    Priority: BACKEND_TYPE env → config file → detection order
    (Anthropic key → Ollama URL → Claude Code binary → none).

    Returns (backend_type, kwargs) for create_backend(), or ("none", {})
    if no backend is available.
    """
    cfg = config or {}

    # 1. Explicit BACKEND_TYPE env var (highest priority)
    backend_type = os.environ.get("BACKEND_TYPE", "").strip()

    # 2. Config file fallback
    if not backend_type:
        backend_type = cfg.get("backend.type", "").strip()

    # Build kwargs from env + config (env wins)
    anthropic_key = os.environ.get(
        "ANTHROPIC_API_KEY", cfg.get("backend.anthropic.api_key", "")
    )
    ollama_host = os.environ.get(
        "OLLAMA_HOST", cfg.get("backend.ollama.url", "http://localhost:11434")
    )
    claude_path = os.environ.get(
        "CLAUDE_PATH", cfg.get("backend.claude_code.path", "claude")
    )
    codex_path = os.environ.get(
        "CODEX_PATH", cfg.get("backend.codex.path", "codex")
    )
    default_model = os.environ.get(
        "GOVERNOR_MODEL", cfg.get("backend.model", "")
    )

    if backend_type:
        # Explicit type — build kwargs for it
        kwargs: dict[str, Any] = {}
        if backend_type == "anthropic":
            kwargs["api_key"] = anthropic_key
        elif backend_type == "ollama":
            kwargs["host"] = ollama_host
        elif backend_type == "claude-code":
            kwargs["claude_path"] = claude_path
        elif backend_type == "codex":
            kwargs["codex_path"] = codex_path
        if default_model:
            kwargs["default_model"] = default_model
        return backend_type, kwargs

    # 3. Auto-detection order: Anthropic key → Claude CLI → Codex CLI → Ollama → none
    if anthropic_key:
        kwargs = {"api_key": anthropic_key}
        if default_model:
            kwargs["default_model"] = default_model
        return "anthropic", kwargs

    if shutil.which(claude_path):
        kwargs = {"claude_path": claude_path}
        if default_model:
            kwargs["default_model"] = default_model
        return "claude-code", kwargs

    if shutil.which(codex_path):
        kwargs = {"codex_path": codex_path}
        if default_model:
            kwargs["default_model"] = default_model
        return "codex", kwargs

    # Ollama is always structurally available (may fail at connection time)
    kwargs = {"host": ollama_host}
    if default_model:
        kwargs["default_model"] = default_model
    return "ollama", kwargs


class DaemonState:
    """Lazy wrapper around governor subsystems for daemon handlers."""

    def __init__(self, governor_dir: Path, mode: str = "general") -> None:
        self.governor_dir = governor_dir
        self.root = governor_dir.parent
        self.mode = mode
        self._config: dict[str, str] | None = None
        self._session_store = None
        self._receipt_system = None
        self._scar_ledger = None
        self._violation_resolver = None
        self._chat_bridge = None
        self._backend_type: str = "none"
        self._backend_kwargs: dict[str, Any] = {}
        self._context_manager = None

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

    @property
    def daemon_config(self) -> dict[str, str]:
        if self._config is None:
            self._config = load_daemon_config(self.governor_dir)
        return self._config

    @property
    def context_manager(self):
        if self._context_manager is None:
            from .context_manager import GovernorContextManager
            self._context_manager = GovernorContextManager(self.governor_dir)
        return self._context_manager

    @property
    def backend_type(self) -> str:
        """Detected backend type (lazy — runs detection on first access)."""
        if self._backend_type == "none" and not self._chat_bridge:
            self._backend_type, self._backend_kwargs = detect_backend(
                self.daemon_config
            )
        return self._backend_type

    @property
    def chat_bridge(self):
        """Lazy-initialized ChatBridge with auto-detected backend.

        Returns None if no backend can be created (e.g. missing API key).
        """
        if self._chat_bridge is None:
            bt, kwargs = detect_backend(self.daemon_config)
            self._backend_type = bt
            self._backend_kwargs = kwargs

            try:
                from .chat_bridge import ChatBridge, create_backend
                # Pop default_model — it's not a create_backend kwarg
                kwargs.pop("default_model", None)
                backend = create_backend(bt, **kwargs)
                self._chat_bridge = ChatBridge(
                    backend=backend,
                    context_manager=self.context_manager,
                    show_ok_footer=True,
                )
            except Exception as e:
                logger.warning("Failed to create chat backend (%s): %s", bt, e)
                return None
        return self._chat_bridge

    @property
    def default_model(self) -> str:
        """Default model from config/env, or empty string."""
        return self._backend_kwargs.get("default_model", "")

    @property
    def trust_principal_from_client(self) -> bool:
        """Whether to trust principal_id from RPC callers.

        When False (default), daemon overwrites client-provided principal_id
        with "untrusted". Enable only for trusted transports (LAN dev, stdio).

        Set via TRUST_PRINCIPAL_FROM_CLIENT=1 env var or
        daemon.trust_principal_from_client=true in daemon.conf.
        """
        env_val = os.environ.get("TRUST_PRINCIPAL_FROM_CLIENT", "").strip()
        if env_val:
            return env_val in ("1", "true", "yes")
        return self.daemon_config.get(
            "daemon.trust_principal_from_client", ""
        ).lower() in ("1", "true", "yes")

    def resolve_principal(self, client_principal: str | None) -> str:
        """Resolve the effective principal_id for a request.

        If trust is enabled and client provides a value, use it.
        Otherwise default to "local".
        """
        if client_principal and self.trust_principal_from_client:
            return client_principal
        if client_principal and not self.trust_principal_from_client:
            logger.debug(
                "principal_id=%r from client ignored (trust not enabled)",
                client_principal,
            )
        return "local"


# =============================================================================
# Handler registration — 26 RPC methods
# =============================================================================


def _emit_chat_receipt(
    state: DaemonState,
    verdict: str,
    content: str,
    run_id: str,
    model: str = "",
    principal_id: str = "local",
) -> "GateReceipt | None":
    """Emit a gate receipt for a chat generation check. Returns the receipt or None."""
    try:
        from .gate_receipt import GateReceipt  # noqa: F811
        receipt = state.receipt_system.emit(
            gate="chat_bridge",
            verdict=verdict,
            subject_kind="chat_response",
            subject_bytes=content.encode("utf-8"),
            evidence_bundle={
                "run_id": run_id,
                "backend_type": state.backend_type,
                "model": model,
            },
            gate_config={"mode": state.mode},
            principal_id=principal_id,
        )
        return receipt
    except Exception:
        logger.error(
            "receipt_emit_failed: chat_bridge gate receipt not written"
            " — audit linkage degraded (verdict=%s, run_id=%s, mode=%s, gov_dir=%s)",
            verdict, run_id, state.mode, state.governor_dir,
            exc_info=True,
        )
        return None


async def _resolve_violation(
    state: DaemonState,
    pending: Any,
    action: Any,
    bridge: Any,
    model: str,
    principal_id: str = "local",
) -> dict:
    """Handle a resolution action for a pending violation.

    Returns a chat-send-shaped result dict.
    """
    from .violation_resolver import ResolutionAction

    if action == ResolutionAction.FIX:
        result = await state.violation_resolver.resolve_fix(
            pending, bridge.backend, model
        )
    elif action == ResolutionAction.REVISE:
        result = state.violation_resolver.resolve_revise(pending)
    else:  # PROCEED
        result = state.violation_resolver.resolve_proceed(pending)

    # Emit resolution receipt on PROCEED for audit trail
    if action == ResolutionAction.PROCEED and result.success:
        try:
            state.receipt_system.emit(
                gate="violation_resolution",
                verdict="proceed",
                subject_kind="exception",
                subject_bytes=(result.exception_id or "").encode("utf-8"),
                evidence_bundle={
                    "exception_id": result.exception_id,
                    "original_receipt_id": getattr(pending, "receipt_id", None),
                    "action": "proceed",
                    "backend_type": state.backend_type,
                    "model": model,
                },
                gate_config={"mode": state.mode},
                principal_id=principal_id,
            )
        except Exception:
            logger.error(
                "receipt_emit_failed: violation_resolution receipt not written"
                " — resolution audit trail broken (exception_id=%s, mode=%s)",
                result.exception_id, state.mode,
                exc_info=True,
            )

    content = ""
    if result.success:
        if result.new_content:
            content = result.new_content
        else:
            content = f"[Governor] {result.message}"
    else:
        content = f"[Governor] Resolution failed: {result.message}"

    return {
        "content": content,
        "model": model,
        "usage": {},
        "violations": [],
        "footer": None,
        "pending": None,
    }


def register_handlers(dispatcher: Dispatcher, state: DaemonState) -> None:
    """Register all daemon RPC handlers."""

    # --- Handshake ---

    async def governor_hello(params: dict) -> dict:
        initialized = state.governor_dir.exists()
        bridge = state.chat_bridge
        has_chat = bridge is not None
        backend_info: dict[str, Any] = {
            "type": state.backend_type,
            "connected": has_chat,
        }
        if state.default_model:
            backend_info["model"] = state.default_model
        return {
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": {
                "chat": has_chat,
                "streaming": has_chat,
                "fix_mode": "candidate_only",
                "sessions": True,
                "intent": True,
                "receipts": True,
                "scars": True,
                "commit": True,
                "backend": backend_info,
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

    # --- Chat ---

    async def chat_send(params: dict) -> dict:
        """Non-streaming governed chat. Full pipeline: pending check → augment → generate → check → receipt."""
        bridge = state.chat_bridge
        if bridge is None:
            raise RuntimeError("No chat backend configured")

        messages_raw = params.get("messages", [])
        model = params.get("model", "") or state.default_model
        context_id = params.get("context_id", "default")
        principal_id = state.resolve_principal(params.get("principal_id"))

        if not messages_raw:
            raise ValueError("Missing required param: messages")

        # Check for pre-existing pending violation BEFORE generation
        pending = state.violation_resolver.get_pending()
        if pending:
            last_msg = messages_raw[-1].get("content", "") if messages_raw else ""
            action = state.violation_resolver.is_resolution_command(last_msg)
            if action:
                result = await _resolve_violation(
                    state, pending, action, bridge, model,
                    principal_id=principal_id,
                )
                return result
            else:
                # Re-present pending violation — don't proceed with generation
                from .violation_resolver import format_violation_prompt
                return {
                    "content": "",
                    "model": model,
                    "usage": {},
                    "violations": pending.violations,
                    "footer": None,
                    "pending": pending.to_dict(),
                }

        from .chat_bridge import ChatMessage, ChatResponse, ViolationPendingResponse

        messages = [
            ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages_raw
        ]

        # Get hooks for violation checking
        ctx = state.context_manager.get_or_create(context_id, mode=state.mode)
        from .chat_bridge import GovernorHooks, _format_governor_footer
        hooks = GovernorHooks(ctx)
        augmented = hooks.augment_messages(messages)

        # Generate
        response = await bridge.backend.chat(augmented, model)
        run_id = uuid.uuid4().hex[:12]

        # Check for blocking violations
        check_result = hooks.check_response_blocking(
            response.content, run_id=run_id
        )

        if isinstance(check_result, ViolationPendingResponse):
            # Blocking violation — emit receipt first, then link to pending
            receipt = _emit_chat_receipt(
                state, "block", response.content, run_id,
                model=model, principal_id=principal_id,
            )
            if receipt is not None:
                # Update the pending violation with the receipt_id
                pending = state.violation_resolver.get_pending()
                if pending is not None:
                    pending.receipt_id = receipt.receipt_id
                    state.violation_resolver._save_pending(pending)
            return {
                "content": response.content,
                "model": response.model,
                "usage": response.usage,
                "violations": check_result.violations,
                "footer": None,
                "pending": check_result.to_dict(),
            }

        # Non-blocking — format footer
        footer = _format_governor_footer(check_result, bridge.show_ok_footer)
        _emit_chat_receipt(
            state, "pass", response.content, run_id,
            model=model, principal_id=principal_id,
        )

        return {
            "content": response.content,
            "model": response.model,
            "usage": response.usage,
            "violations": check_result.violations,
            "footer": footer,
            "pending": None,
        }

    async def chat_stream(params: dict, notify: NotifyFn) -> dict:
        """Streaming governed chat. Sends chat.delta notifications, then final result."""
        bridge = state.chat_bridge
        if bridge is None:
            raise RuntimeError("No chat backend configured")

        messages_raw = params.get("messages", [])
        model = params.get("model", "") or state.default_model
        context_id = params.get("context_id", "default")
        principal_id = state.resolve_principal(params.get("principal_id"))

        if not messages_raw:
            raise ValueError("Missing required param: messages")

        # Check for pre-existing pending violation BEFORE generation
        pending = state.violation_resolver.get_pending()
        if pending:
            last_msg = messages_raw[-1].get("content", "") if messages_raw else ""
            action = state.violation_resolver.is_resolution_command(last_msg)
            if action:
                result = await _resolve_violation(
                    state, pending, action, bridge, model,
                    principal_id=principal_id,
                )
                return result
            else:
                return {
                    "content": "",
                    "model": model,
                    "usage": {},
                    "violations": pending.violations,
                    "footer": None,
                    "pending": pending.to_dict(),
                }

        from .chat_bridge import ChatMessage, ViolationPendingResponse

        messages = [
            ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages_raw
        ]

        # Get hooks
        ctx = state.context_manager.get_or_create(context_id, mode=state.mode)
        from .chat_bridge import GovernorHooks, _format_governor_footer
        hooks = GovernorHooks(ctx)
        augmented = hooks.augment_messages(messages)

        # Stream generation, sending deltas as notifications
        accumulated: list[str] = []
        async for chunk in bridge.backend.stream(augmented, model):
            if chunk.content:
                accumulated.append(chunk.content)
                await notify("chat.delta", {"content": chunk.content})
            if chunk.finish_reason is not None:
                break

        full_content = "".join(accumulated)
        run_id = uuid.uuid4().hex[:12]

        # Run governance check on accumulated content
        check_result = hooks.check_response_blocking(
            full_content, run_id=run_id
        )

        if isinstance(check_result, ViolationPendingResponse):
            receipt = _emit_chat_receipt(
                state, "block", full_content, run_id,
                model=model, principal_id=principal_id,
            )
            if receipt is not None:
                pending = state.violation_resolver.get_pending()
                if pending is not None:
                    pending.receipt_id = receipt.receipt_id
                    state.violation_resolver._save_pending(pending)
            return {
                "content": full_content,
                "model": model,
                "usage": {},
                "violations": check_result.violations,
                "footer": None,
                "pending": check_result.to_dict(),
            }

        footer = _format_governor_footer(check_result, bridge.show_ok_footer)
        _emit_chat_receipt(
            state, "pass", full_content, run_id,
            model=model, principal_id=principal_id,
        )

        return {
            "content": full_content,
            "model": model,
            "usage": {},
            "violations": check_result.violations,
            "footer": footer,
            "pending": None,
        }

    async def chat_models(params: dict) -> dict:
        """List available models from the current backend."""
        bridge = state.chat_bridge
        if bridge is None:
            return {"models": []}
        try:
            models = await bridge.list_models()
        except Exception:
            return {"models": []}
        return {"models": models}

    async def chat_backend(params: dict) -> dict:
        """Return current backend info."""
        bridge = state.chat_bridge
        connected = bridge is not None
        result: dict[str, Any] = {
            "type": state.backend_type,
            "connected": connected,
        }
        if state.default_model:
            result["model"] = state.default_model
        return result

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

    # --- Selfcheck ---

    async def governor_selfcheck(params: dict) -> dict:
        """Run self-check on governor store integrity."""
        from .selfcheck import run_selfcheck
        scope = params.get("scope", "fast")
        items = run_selfcheck(state.governor_dir, scope=scope)
        return {
            "items": [i.to_dict() for i in items],
            "overall": "ok" if all(i.status == "ok" for i in items) else "degraded",
        }

    dispatcher.register("governor.selfcheck", governor_selfcheck)

    dispatcher.register("chat.send", chat_send)
    dispatcher.register_streaming("chat.stream", chat_stream)
    dispatcher.register("chat.models", chat_models)
    dispatcher.register("chat.backend", chat_backend)


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
            response = await dispatcher.dispatch(msg, writer=writer)
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
                response = await dispatcher.dispatch(msg, writer=writer)
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
