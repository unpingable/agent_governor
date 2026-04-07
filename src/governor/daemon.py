# SPDX-License-Identifier: Apache-2.0
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
import time
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
    """JSON-RPC 2.0 method dispatcher with read/mutating classification.

    Every registered method is classified as ``read_only`` (default) or
    ``mutating``.  The classification is metadata today (logged, exposed
    via ``get_method_info``); it becomes a hard gate when TCP transport
    lands.
    """

    def __init__(self, *, allow_mutating: bool = True) -> None:
        self._handlers: dict[str, Handler] = {}
        self._streaming_handlers: dict[str, StreamingHandler] = {}
        self._method_flags: dict[str, str] = {}  # method → "read_only" | "mutating"
        self._mutating_allowed = allow_mutating

    def register(
        self,
        method: str,
        handler: Handler,
        *,
        mutating: bool = False,
    ) -> None:
        self._handlers[method] = handler
        self._method_flags[method] = "mutating" if mutating else "read_only"

    def register_streaming(
        self,
        method: str,
        handler: StreamingHandler,
        *,
        mutating: bool = False,
    ) -> None:
        """Register a streaming handler that can send notifications during execution."""
        self._streaming_handlers[method] = handler
        self._method_flags[method] = "mutating" if mutating else "read_only"

    def is_mutating(self, method: str) -> bool:
        """Return True if *method* is classified as mutating."""
        return self._method_flags.get(method) == "mutating"

    def get_method_info(self) -> dict[str, str]:
        """Return {method: "read_only"|"mutating"} for all registered methods."""
        return dict(self._method_flags)

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

        # Mutating gate: daemon-side enforcement
        if self.is_mutating(method) and not self._mutating_allowed:
            if is_notification:
                return None
            return _error_response(
                request_id, AUTH_ERROR,
                f"Mutating method {method!r} blocked by daemon policy"
            )

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
    Config file is INI format with sections:
      - [backend]  — backend type, API keys, model names
      - [daemon]   — allow_mutating_rpc, socket path
      - [security] — v3 placeholder (commented out in v2; will hold
                     auth_method, principal_ref hashing, mTLS config)
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
        from .session import get_session_id

        self.governor_dir = governor_dir
        self.root = governor_dir.parent
        self.mode = mode
        self.session_id = get_session_id()
        self._config: dict[str, str] | None = None
        self._session_store = None
        self._receipt_system = None
        self._scar_ledger = None
        self._violation_resolver = None
        self._chat_bridge = None
        self._backend_type: str = "none"
        self._backend_kwargs: dict[str, Any] = {}
        self._context_manager = None
        self._correlator_telemetry = None
        self._scope_governor = None
        self._stability_store = None
        self._stability_auditor = None
        self._lane_router = None
        self._cascade_executor = None
        self._artifact_store = None
        self._regime_detector = None
        self._cooldown_store = None
        self._receipt_v1_store = None
        self._claim_correlation_store = None
        self._policy_rule_set = None
        self._policy_load_status: str | None = None
        self._policy_loaded_at: str | None = None
        self._policy_content_hash: str | None = None
        self._chain_rule_set = None
        self._chain_load_status: str | None = None
        self._chain_content_hash: str | None = None
        self._chain_loaded_at: str | None = None
        self._chain_action_logs = None
        self._chain_mode: str | None = None
        self._signal_store = None
        self._runtime_supervisor = None

    @property
    def chain_mode(self) -> str:
        """Runtime chain enforcement mode. Defaults to detect_only.

        Source: CHAIN_MODE env var → chain.mode in daemon.conf → detect_only.
        """
        if self._chain_mode is None:
            raw = os.environ.get(
                "CHAIN_MODE",
                self.daemon_config.get("chain.mode", "detect_only"),
            ).strip().lower()
            from .chain_gate import ChainMode
            try:
                self._chain_mode = ChainMode(raw).value
            except ValueError:
                logger.warning("Invalid CHAIN_MODE=%r, defaulting to detect_only", raw)
                self._chain_mode = ChainMode.DETECT_ONLY.value
        return self._chain_mode

    @property
    def claim_correlation_store(self):
        if self._claim_correlation_store is None:
            from .claim_correlation import ClaimCorrelationStore
            self._claim_correlation_store = ClaimCorrelationStore.load(
                self.governor_dir
            )
        return self._claim_correlation_store

    @property
    def policy_rule_set(self):
        """Lazy-loaded policy rule set. Cached for daemon lifetime (no auto-reload).

        Sources (in order): $GOVERNOR_DIR/policy.json → default deny-all.
        Corrupt files fall back to default with load_status='corrupt_file_fallback'.
        """
        if self._policy_rule_set is None:
            from .policy_engine import load_policy, default_policy
            policy_path = self.governor_dir / "policy.json"
            if policy_path.exists():
                try:
                    raw = policy_path.read_bytes()
                    self._policy_content_hash = hashlib.sha256(raw).hexdigest()
                    self._policy_rule_set = load_policy(policy_path)
                    self._policy_load_status = "loaded"
                except Exception:
                    logger.warning(
                        "Failed to load policy.json, using default deny-all",
                        exc_info=True,
                    )
                    try:
                        self._policy_content_hash = hashlib.sha256(
                            policy_path.read_bytes()
                        ).hexdigest()
                    except Exception:
                        self._policy_content_hash = None
                    self._policy_rule_set = default_policy()
                    self._policy_load_status = "corrupt_file_fallback"
            else:
                self._policy_rule_set = default_policy()
                self._policy_load_status = "missing_file"
                self._policy_content_hash = None
            self._policy_loaded_at = datetime.now(
                timezone.utc
            ).isoformat()
            logger.info(
                "policy_loaded: source=%s bundle=%s version=%s hash=%s",
                self._policy_load_status,
                self._policy_rule_set.policy_bundle_id,
                self._policy_rule_set.policy_bundle_version,
                self._policy_content_hash,
            )
        return self._policy_rule_set

    @property
    def chain_rule_set(self):
        """Lazy-loaded chain composition rules. Cached for daemon lifetime.

        Sources: $GOVERNOR_DIR/chain_rules.json → empty (no rules).
        Four load states: loaded, missing_policy, corrupt_fallback, loaded_empty.
        """
        if self._chain_rule_set is None:
            from .chain_gate import load_chain_rules
            rules_path = self.governor_dir / "chain_rules.json"
            self._chain_rule_set, self._chain_load_status = load_chain_rules(
                rules_path
            )
            if rules_path.exists():
                try:
                    self._chain_content_hash = hashlib.sha256(
                        rules_path.read_bytes()
                    ).hexdigest()
                except Exception:
                    self._chain_content_hash = None
            else:
                self._chain_content_hash = None
            self._chain_loaded_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "chain_rules_loaded: status=%s rule_count=%d hash=%s",
                self._chain_load_status,
                len(self._chain_rule_set.rules),
                self._chain_content_hash,
            )
        return self._chain_rule_set

    @property
    def chain_action_logs(self):
        """Lazy-initialized action log store for chain composition gate."""
        if self._chain_action_logs is None:
            from .chain_gate import ActionLogStore
            self._chain_action_logs = ActionLogStore(
                self.governor_dir / "chain_logs"
            )
        return self._chain_action_logs

    @property
    def cooldown_store(self):
        if self._cooldown_store is None:
            from .lanes import CooldownStore
            self._cooldown_store = CooldownStore(
                path=self.governor_dir / "cooldown.jsonl",
            )
        return self._cooldown_store

    @property
    def lane_router(self):
        if self._lane_router is None:
            from .lanes import LaneRouter, ArtifactReuseStore
            self._lane_router = LaneRouter(
                artifact_store=self.artifact_store,
                receipt_system=self.receipt_system,
                cooldown_store=self.cooldown_store,
            )
        return self._lane_router

    @property
    def artifact_store(self):
        if self._artifact_store is None:
            from .lanes import ArtifactReuseStore
            artifacts_dir = self.governor_dir / "artifacts"
            self._artifact_store = ArtifactReuseStore(artifacts_dir)
        return self._artifact_store

    @property
    def cascade_executor(self):
        if self._cascade_executor is None:
            from .lanes import CascadeExecutor
            self._cascade_executor = CascadeExecutor(
                lane_router=self.lane_router,
                artifact_store=self.artifact_store,
                receipt_system=self.receipt_system,
                cooldown_store=self.cooldown_store,
            )
        return self._cascade_executor

    # Max age (seconds) for persisted regime state.  If regime.json is
    # older than this the detector starts fresh so we don't silently
    # de-risk lane routing from a stale "elastic."
    _REGIME_MAX_AGE_S: float = 600.0  # 10 minutes

    @property
    def regime_detector(self):
        if self._regime_detector is None:
            from .regime import RegimeDetector
            regime_file = self.governor_dir / "regime.json"
            if regime_file.exists():
                import json as _json
                try:
                    mtime = regime_file.stat().st_mtime
                    age = time.time() - mtime
                    if age > self._REGIME_MAX_AGE_S:
                        logger.info(
                            "regime.json is %.0fs old (max %ds), starting fresh",
                            age, self._REGIME_MAX_AGE_S,
                        )
                        self._regime_detector = RegimeDetector()
                    else:
                        data = _json.loads(regime_file.read_text())
                        self._regime_detector = RegimeDetector.from_dict(data)
                except Exception:
                    self._regime_detector = RegimeDetector()
            else:
                self._regime_detector = RegimeDetector()
        return self._regime_detector

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
    def receipt_v1_store(self):
        if self._receipt_v1_store is None:
            from receipt_v1.store import JsonlStore
            self._receipt_v1_store = JsonlStore(
                self.governor_dir / "receipts" / "receipt_v1.jsonl"
            )
        return self._receipt_v1_store

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
    def correlator_telemetry(self):
        if self._correlator_telemetry is None:
            from .correlator_telemetry import CorrelatorTelemetry
            self._correlator_telemetry = CorrelatorTelemetry.load(
                self.governor_dir
            )
        return self._correlator_telemetry

    @property
    def scope_governor(self):
        if self._scope_governor is None:
            from .scope import ScopeGovernor
            self._scope_governor = ScopeGovernor.load(self.governor_dir)
        return self._scope_governor

    @property
    def signal_store(self):
        if self._signal_store is None:
            from .signal_store import SignalStore
            signals_dir = self.governor_dir / "signals"
            signals_dir.mkdir(exist_ok=True)
            db_path = signals_dir / "signals.db"
            jsonl_path = signals_dir / "signals.jsonl"
            self._signal_store = SignalStore(db_path)
            if jsonl_path.exists():
                self._signal_store.ingest_from_jsonl(jsonl_path)
        return self._signal_store

    @property
    def runtime_supervisor(self):
        if self._runtime_supervisor is None:
            from .runtime.supervisor import SessionSupervisor
            runtime_dir = self.governor_dir / "runtime"
            runtime_dir.mkdir(exist_ok=True)
            self._runtime_supervisor = SessionSupervisor(state_dir=runtime_dir)
        return self._runtime_supervisor

    @property
    def stability_store(self):
        if self._stability_store is None:
            from .semantic_stability import StabilityStore
            self._stability_store = StabilityStore(self.governor_dir)
        return self._stability_store

    @property
    def stability_auditor(self):
        if self._stability_auditor is None:
            from .semantic_stability import StabilityAuditor
            self._stability_auditor = StabilityAuditor()
        return self._stability_auditor

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
                # Fiction mode: governance must never surface in-band
                show_ok = self.mode not in ("fiction",)
                self._chat_bridge = ChatBridge(
                    backend=backend,
                    context_manager=self.context_manager,
                    show_ok_footer=show_ok,
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
# Handler registration — 36 RPC methods
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
                "signals_preflight": True,
                "backend": backend_info,
            },
            "governor": {
                "context_id": state.governor_dir.name
                if state.governor_dir.name != ".governor"
                else "default",
                "mode": state.mode,
                "initialized": initialized,
                "session_id": state.session_id,
            },
            "session": {
                "session_id": state.session_id,
                "principal": None,           # v3: authenticated identity
                "principal_ref": None,       # v3: H(principal) — matches receipt field
                "auth_method": "local",      # v3: "mtls" | "token" | "local"
                "session_token": None,       # v3: cryptographic session token
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

    # --- Receipt v1 (new format — separate from legacy gate receipts) ---

    async def receipts_v1_list(params: dict) -> list:
        """List Receipt v1 records.

        Params:
            session_id (str?): Filter by actor.session_id.
            since (str?): timestamp_wall (ISO 8601 UTC, e.g. "2026-02-19T12:00:00Z").
                          Lexicographic >= comparison. Both sides must be UTC with Z suffix.
            limit (int?): Maximum number of receipts to return.
        """
        session_id = params.get("session_id")
        since = params.get("since")
        limit = params.get("limit")
        if limit is not None:
            limit = int(limit)
        store = state.receipt_v1_store
        results = []
        for receipt in store.iter_receipts(
            session_id=session_id, since=since, limit=limit
        ):
            results.append(receipt.to_dict())
        return results

    async def receipts_v1_detail(params: dict) -> dict:
        receipt_id = params.get("receipt_id")
        if not receipt_id:
            raise ValueError("Missing required param: receipt_id")
        receipt = state.receipt_v1_store.get_receipt(receipt_id)
        if receipt is None:
            raise ValueError(f"Receipt v1 not found: {receipt_id}")
        return {"receipt": receipt.to_dict()}

    async def receipts_v1_verify(params: dict) -> dict:
        """Verify chain integrity across stored Receipt v1 records.

        Returns structured result with chain metadata that UIs need:
        valid, errors (structured), warnings, count, endpoints, gaps.
        """
        session_id = params.get("session_id")
        store = state.receipt_v1_store

        # Collect all dicts in chronological order for metadata extraction
        dicts = store._all_dicts_chronological()
        if session_id is not None:
            dicts = [
                d for d in dicts
                if d.get("actor", {}).get("session_id") == session_id
            ]

        result = store.verify_chain(session_id=session_id)

        # Structure errors: extract receipt_id from error messages when possible
        import re
        _SEQ_RE = re.compile(r"seq=(\d+)")
        structured_errors = []
        for err in result.errors:
            entry: dict[str, Any] = {"message": err}
            m = _SEQ_RE.search(err)
            if m:
                seq = int(m.group(1))
                # Find receipt_id for this seq
                for d in dicts:
                    if d.get("chain", {}).get("seq") == seq:
                        entry["receipt_id"] = d.get("receipt_id")
                        break
            structured_errors.append(entry)

        # Chain metadata
        first_id = dicts[0].get("receipt_id") if dicts else None
        last_id = dicts[-1].get("receipt_id") if dicts else None

        # Detect gaps from warnings
        _GAP_RE = re.compile(r"Seq gap: (\d+) -> (\d+)")
        gaps = []
        for w in result.warnings:
            m = _GAP_RE.search(w)
            if m:
                gaps.append({"from_seq": int(m.group(1)), "to_seq": int(m.group(2))})

        return {
            "valid": result.valid,
            "errors": structured_errors,
            "warnings": result.warnings,
            "count": len(dicts),
            "first_receipt_id": first_id,
            "last_receipt_id": last_id,
            "gaps": gaps,
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

        # --- Optional lane routing (opt-in) ---
        use_lanes = params.get("use_lanes", False)
        if use_lanes:
            try:
                from .lanes import CascadeResult, regime_to_risk_class
                lr = state.lane_router
                last_content = messages_raw[-1].get("content", "")

                # Derive risk_class from regime if not explicitly provided.
                explicit_risk = params.get("risk_class")
                if explicit_risk:
                    risk_class = explicit_risk
                    risk_class_source = "explicit"
                else:
                    regime_val = state.regime_detector.current_regime.value
                    risk_class, known = regime_to_risk_class(regime_val)
                    risk_class_source = f"regime:{regime_val}"
                    if not known:
                        logger.warning(
                            "Unknown regime %r → fail-open standard; "
                            "regime detector may be broken",
                            regime_val,
                        )
                        risk_class_source = f"regime:{regime_val}(unknown)"

                plan = lr.route(
                    task_hint=params.get("task_hint"),
                    risk_class=risk_class,
                    has_side_effects=params.get("has_side_effects", False),
                    format_strict=params.get("format_strict", False),
                    context_heavy=params.get("context_heavy", False),
                )
                routed_model = plan.model

                def sync_generate(prompt: str, mdl: str) -> str:
                    import asyncio as _aio
                    import concurrent.futures
                    from .chat_bridge import ChatMessage as CM
                    async def _gen():
                        msgs = [CM(role="user", content=prompt)]
                        resp = await bridge.backend.chat(msgs, mdl)
                        return resp.content
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        fut = pool.submit(_aio.run, _gen())
                        return fut.result(timeout=120)

                executor = state.cascade_executor
                cascade_result = executor.execute(
                    plan=plan,
                    prompt=last_content,
                    generate_fn=sync_generate,
                )
                run_id = uuid.uuid4().hex[:12]
                _emit_chat_receipt(
                    state, "pass", cascade_result.output, run_id,
                    model=cascade_result.model_used, principal_id=principal_id,
                )
                return {
                    "content": cascade_result.output,
                    "model": cascade_result.model_used,
                    "usage": {},
                    "violations": [],
                    "footer": None,
                    "pending": None,
                    "routing": {
                        "enabled": True,
                        "lane": cascade_result.lane_used,
                        "escalated": cascade_result.escalated,
                        "artifact_hit": cascade_result.artifact_hit,
                        "risk_class": risk_class,
                        "risk_class_source": risk_class_source,
                    },
                }
            except Exception as e:
                logger.warning("Lane routing failed, falling back: %s", e)
                _send_lanes_fallback_reason = str(e)
                _send_lanes_fell_through = True
        else:
            _send_lanes_fell_through = False
            _send_lanes_fallback_reason = ""

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

        result = {
            "content": response.content,
            "model": response.model,
            "usage": response.usage,
            "violations": check_result.violations,
            "footer": footer,
            "pending": None,
        }
        if use_lanes and _send_lanes_fell_through:
            result["routing"] = {
                "enabled": False,
                "reason": _send_lanes_fallback_reason,
            }
        return result

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

        # --- Optional lane routing (opt-in) ---
        use_lanes = params.get("use_lanes", False)
        if use_lanes:
            try:
                from .lanes import (
                    CascadeResult, regime_to_risk_class, _MAX_VALIDATION_BUFFER,
                )
                lr = state.lane_router
                last_content = messages_raw[-1].get("content", "")

                # Derive risk_class from regime if not explicitly provided.
                explicit_risk = params.get("risk_class")
                if explicit_risk:
                    risk_class = explicit_risk
                    risk_class_source = "explicit"
                else:
                    regime_val = state.regime_detector.current_regime.value
                    risk_class, known = regime_to_risk_class(regime_val)
                    risk_class_source = f"regime:{regime_val}"
                    if not known:
                        logger.warning(
                            "Unknown regime %r → fail-open standard; "
                            "regime detector may be broken",
                            regime_val,
                        )
                        risk_class_source = f"regime:{regime_val}(unknown)"

                plan = lr.route(
                    task_hint=params.get("task_hint"),
                    risk_class=risk_class,
                    has_side_effects=params.get("has_side_effects", False),
                    format_strict=params.get("format_strict", False),
                    context_heavy=params.get("context_heavy", False),
                )
                routed_model = plan.model

                from .chat_bridge import ChatMessage as CM
                stream_msgs = [
                    CM(role=m.get("role", "user"), content=m.get("content", ""))
                    for m in messages_raw
                ]

                # Stream through routed model, buffer for post-hoc validation
                accumulated: list[str] = []
                lanes_stream_usage: dict[str, int] = {}
                is_cancelled = False
                validation_scope = "full"
                validators_failed: list[str] = []
                try:
                    async for chunk in bridge.backend.stream(stream_msgs, routed_model):
                        if chunk.content:
                            accumulated.append(chunk.content)
                            await notify("chat.delta", {"content": chunk.content})
                        if chunk.finish_reason is not None:
                            if chunk.usage:
                                lanes_stream_usage = chunk.usage
                            break
                except Exception:
                    is_cancelled = True
                    validation_scope = "skipped"

                full_content = "".join(accumulated)
                run_id = uuid.uuid4().hex[:12]

                # Post-hoc validator check on buffered content
                if not is_cancelled:
                    if len(full_content) > _MAX_VALIDATION_BUFFER:
                        validation_scope = "truncated"
                    executor = state.cascade_executor
                    v_passed, v_failed = executor._run_validators(
                        plan.validators,
                        full_content[:_MAX_VALIDATION_BUFFER],
                    )
                    validators_failed = v_failed

                # Record to cooldown store (always, including cancel)
                cooldown_store = state.cooldown_store
                if cooldown_store is not None:
                    try:
                        from .lanes import CooldownEntry, _cooldown_key
                        ck = _cooldown_key(
                            routed_model, plan.lane,
                            risk_class, plan.task_hint, validators_failed,
                            policy_version=lr.policy_version,
                        )
                        is_failure = bool(validators_failed) or is_cancelled
                        entry = CooldownEntry(
                            cooldown_key=ck,
                            model=routed_model,
                            lane=plan.lane,
                            risk_class=risk_class,
                            task_hint=plan.task_hint,
                            validators_failed=validators_failed,
                            probe_decision=None,
                            escalated=False,
                            is_failure=is_failure,
                            timestamp=time.strftime(
                                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(),
                            ),
                            policy_version=lr.policy_version,
                            is_cancelled=is_cancelled,
                            validation_scope=validation_scope,
                        )
                        cooldown_store.record_entry(entry)
                    except Exception:
                        logger.debug(
                            "cooldown store stream record failed", exc_info=True,
                        )

                _emit_chat_receipt(
                    state, "pass", full_content, run_id,
                    model=routed_model, principal_id=principal_id,
                )

                return {
                    "content": full_content,
                    "model": routed_model,
                    "usage": lanes_stream_usage,
                    "violations": [],
                    "footer": None,
                    "pending": None,
                    "routing": {
                        "enabled": True,
                        "lane": plan.lane,
                        "risk_class": risk_class,
                        "risk_class_source": risk_class_source,
                        "validators_failed": validators_failed,
                        "validation_scope": validation_scope,
                        "is_cancelled": is_cancelled,
                    },
                }
            except Exception as e:
                logger.warning("Lane routing failed in stream, falling back: %s", e)
                # Fall through to normal path with explicit routing disabled
                _lanes_fallback_reason = str(e)
                _lanes_fell_through = True
        else:
            _lanes_fell_through = False
            _lanes_fallback_reason = ""

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
        stream_usage: dict[str, int] = {}
        async for chunk in bridge.backend.stream(augmented, model):
            if chunk.content:
                accumulated.append(chunk.content)
                await notify("chat.delta", {"content": chunk.content})
            if chunk.finish_reason is not None:
                if chunk.usage:
                    stream_usage = chunk.usage
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
                "usage": stream_usage,
                "violations": check_result.violations,
                "footer": None,
                "pending": check_result.to_dict(),
            }

        footer = _format_governor_footer(check_result, bridge.show_ok_footer)
        _emit_chat_receipt(
            state, "pass", full_content, run_id,
            model=model, principal_id=principal_id,
        )

        result = {
            "content": full_content,
            "model": model,
            "usage": stream_usage,
            "violations": check_result.violations,
            "footer": footer,
            "pending": None,
        }
        # When use_lanes was requested but failed, include routing disabled info
        if use_lanes and _lanes_fell_through:
            result["routing"] = {
                "enabled": False,
                "reason": _lanes_fallback_reason,
            }
        return result

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

    async def governor_methods(params: dict) -> dict:
        """List all registered RPC methods with classification."""
        info = dispatcher.get_method_info()
        methods = [
            {"method": m, "classification": c}
            for m, c in sorted(info.items())
        ]
        return {"methods": methods, "count": len(methods)}

    dispatcher.register("governor.hello", governor_hello)
    dispatcher.register("governor.now", governor_now)
    dispatcher.register("governor.status", governor_status)
    dispatcher.register("governor.methods", governor_methods)

    dispatcher.register("sessions.list", sessions_list)
    dispatcher.register("sessions.create", sessions_create, mutating=True)
    dispatcher.register("sessions.delete", sessions_delete, mutating=True)
    dispatcher.register("sessions.get", sessions_get)

    dispatcher.register("intent.templates", intent_templates)
    dispatcher.register("intent.schema", intent_schema)
    dispatcher.register("intent.validate", intent_validate)
    dispatcher.register("intent.compile", intent_compile, mutating=True)
    dispatcher.register("intent.policy", intent_policy)

    dispatcher.register("receipts.list", receipts_list)
    dispatcher.register("receipts.detail", receipts_detail)

    dispatcher.register("receipts_v1.list", receipts_v1_list)
    dispatcher.register("receipts_v1.detail", receipts_v1_detail)
    dispatcher.register("receipts_v1.verify", receipts_v1_verify)

    dispatcher.register("scars.list", scars_list)
    dispatcher.register("scars.history", scars_history)

    # --- Correlator ---

    async def correlator_status(params: dict) -> dict:
        ct = state.correlator_telemetry
        metrics = ct.get_metrics()
        result: dict[str, Any] = {"metrics": metrics}
        diag = ct.get_latest_diagnostic()
        if diag:
            result["latest"] = diag.to_dict()
        return result

    async def correlator_history(params: dict) -> list:
        limit = min(max(int(params.get("limit", 50)), 1), 1000)
        ct = state.correlator_telemetry
        return [d.to_dict() for d in ct.get_history(limit=limit)]

    async def correlator_kvector(params: dict) -> dict | None:
        ct = state.correlator_telemetry
        kv = ct.get_latest_k_vector()
        if kv is None:
            return None
        return kv.to_dict()

    dispatcher.register("correlator.status", correlator_status)
    dispatcher.register("correlator.history", correlator_history)
    dispatcher.register("correlator.kvector", correlator_kvector)

    dispatcher.register("commit.pending", commit_pending)
    dispatcher.register("commit.fix", commit_fix, mutating=True)
    dispatcher.register("commit.revise", commit_revise, mutating=True)
    dispatcher.register("commit.proceed", commit_proceed, mutating=True)
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

    # --- Operator snapshot + trace ---

    # Hard caps to prevent operator.snapshot from becoming a CLI avalanche
    # over JSON. Rollup sections are already fixed-shape (one dict each).
    _SNAPSHOT_MAX_SUGGESTIONS = 5
    _SNAPSHOT_MAX_RECEIPT_ITEMS = 5  # recent_receipts already capped by loader
    _TRACE_MAX_EVENTS = 100

    async def operator_snapshot(params: dict) -> dict:
        """Full operator snapshot: rollup + doctor checks + suggestions.

        Response is overview-only. Large lists are capped; callers must
        use dedicated RPC methods (receipts.list, scars.history, etc.)
        for full data.
        """
        from .status_rollup import build_status_rollup
        from .operator_snapshot import classify_rollup, count_checks

        rollup = await asyncio.to_thread(build_status_rollup, state.governor_dir)
        checks = classify_rollup(rollup)
        counts = count_checks(checks)

        suggestions = []
        for c in checks:
            if c.next_commands:
                suggestions.append({
                    "cmd": c.next_commands[0],
                    "why": c.summary,
                    "severity": c.status,
                })

        rollup_dict = rollup.to_dict()

        # Cap receipt items in rollup to prevent payload bloat
        rcpt = rollup_dict.get("recent_receipts", {})
        items = rcpt.get("items", [])
        truncated = False
        if len(items) > _SNAPSHOT_MAX_RECEIPT_ITEMS:
            rcpt["items"] = items[:_SNAPSHOT_MAX_RECEIPT_ITEMS]
            truncated = True

        return {
            "schema": "operator-snapshot/1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "backend": "daemon",
            "gov_dir": str(state.governor_dir),
            "rollup": rollup_dict,
            "checks": [c.to_dict() for c in checks],
            "counts": counts,
            "suggestions": suggestions[:_SNAPSHOT_MAX_SUGGESTIONS],
            "truncated": truncated,
            "limits": {
                "suggestions": _SNAPSHOT_MAX_SUGGESTIONS,
                "receipt_items": _SNAPSHOT_MAX_RECEIPT_ITEMS,
            },
        }

    async def trace_tail(params: dict) -> dict:
        """Tail the unified trace timeline.

        Limit is clamped to _TRACE_MAX_EVENTS to prevent unbounded responses.
        Fetches limit+1 to detect truncation accurately (avoids false positive
        when source has exactly limit events).
        """
        from .operator_snapshot import collect_trace_events

        limit = min(max(int(params.get("limit", 20)), 1), _TRACE_MAX_EVENTS)
        source = params.get("source")

        # Fetch one extra to detect whether more events exist
        events = await asyncio.to_thread(
            collect_trace_events, state.governor_dir, limit + 1, source
        )
        truncated = len(events) > limit
        if truncated:
            events = events[:limit]

        return {
            "events": [e.to_dict() for e in events],
            "truncated": truncated,
            "limit": limit,
            "max_limit": _TRACE_MAX_EVENTS,
        }

    dispatcher.register("operator.snapshot", operator_snapshot)
    dispatcher.register("trace.tail", trace_tail)

    # --- Scope ---

    async def scope_status(params: dict) -> dict:
        sg = state.scope_governor
        return sg.get_metrics()

    async def scope_check(params: dict) -> dict:
        from .scope import Scope
        sg = state.scope_governor
        tool_id = params.get("tool_id", "")
        if not tool_id:
            return {"allowed": False, "reason": "tool_id is required"}
        scope_dict = params.get("scope", {})
        requested = Scope.from_dict(scope_dict)
        ok, err = sg.check_tool(tool_id, requested)
        return {"allowed": ok, "reason": err}

    async def scope_escalate(params: dict) -> dict:
        from .scope import EscalationRequest
        sg = state.scope_governor
        req = EscalationRequest.from_dict(params.get("request", params))
        result = sg.escalate(req, receipt_system=state.receipt_system)
        sg.save(state.governor_dir)
        return result.to_dict()

    async def scope_grants(params: dict) -> list:
        sg = state.scope_governor
        show_all = params.get("all", False)
        grants = sg.get_all_grants() if show_all else sg.get_active_grants()
        return [g.to_dict() for g in grants]

    dispatcher.register("scope.status", scope_status)
    dispatcher.register("scope.check", scope_check)
    dispatcher.register("scope.escalate", scope_escalate, mutating=True)
    dispatcher.register("scope.grants", scope_grants)

    # --- Semantic Stability ---

    async def stability_status(params: dict) -> dict:
        store = state.stability_store
        auditor = state.stability_auditor
        results = store.query(limit=1)
        return {
            "config": auditor.config.to_dict(),
            "total_audits": store.count(),
            "latest": results[0].to_dict() if results else None,
        }

    async def stability_audit(params: dict) -> dict:
        from .semantic_stability import StabilityAuditor, StabilityConfig
        text = params.get("text", "")
        if not text:
            return {"error": "text parameter required"}
        if len(text) > 100_000:
            return {"error": "text exceeds 100KB limit"}
        config_dict = params.get("config", {})
        config = StabilityConfig.from_dict(config_dict) if config_dict else StabilityConfig()
        config.sample_rate = 1.0  # Force audit when explicitly requested
        auditor = StabilityAuditor(config)

        # Identity function: produces a baseline audit (zero divergence).
        # A real audit requires a backend generate function.
        def echo_fn(p: str) -> str:
            return p

        result = auditor.audit(text, text, echo_fn, receipt_system=state.receipt_system)
        result_dict = result.to_dict()
        result_dict["backend"] = "none"  # Flag: identity fallback, not real audit
        state.stability_store.append(result)
        return result_dict

    async def stability_history(params: dict) -> list:
        limit = min(max(int(params.get("limit", 50)), 1), 1000)
        store = state.stability_store
        return [r.to_dict() for r in store.query(limit=limit)]

    async def stability_probe(params: dict) -> dict:
        from .semantic_stability import ProbeContext, PromptSegment

        text = params.get("text", "")
        if not text:
            return {"error": "text parameter required"}
        if len(text) > 100_000:
            return {"error": "text exceeds 100KB limit"}

        # Build ProbeContext from params
        ctx_dict = params.get("context", {})
        deep = params.get("deep", False)

        # Build typed segments if provided
        trusted_segments = None
        raw_segments = ctx_dict.get("trusted_segments")
        if raw_segments and isinstance(raw_segments, list):
            trusted_segments = [
                PromptSegment.make(
                    text=s.get("text", ""),
                    trust=s.get("trust", "untrusted"),
                    seg_class=s.get("seg_class", "context"),
                )
                for s in raw_segments
                if isinstance(s, dict)
            ]

        context = ProbeContext(
            has_side_effects=ctx_dict.get("has_side_effects", False),
            approx_words=ctx_dict.get("approx_words", len(text.split())),
            is_long_prompt=ctx_dict.get("is_long_prompt", len(text.split()) > 1500 or len(text) > 8000),
            is_strict_format=ctx_dict.get("is_strict_format", False),
            is_retrieval_heavy=ctx_dict.get("is_retrieval_heavy", False),
            risk_class=ctx_dict.get("risk_class", "standard"),
            trusted_segments=trusted_segments,
            envelope_mode=ctx_dict.get("envelope_mode", "strict"),
            dry_run=False,  # Never dry_run in RPC — require backend
        )

        # Require a real backend — no echo fallback in RPC
        bridge = state.chat_bridge
        if bridge is None:
            return {"error": "stability.probe requires a configured backend (no dry_run in RPC)"}

        # Wrap async backend.chat() into a sync generate_fn for the probe.
        # The probe runs inside an async handler, so we use asyncio to bridge.
        from .chat_bridge import ChatMessage as CM
        backend = bridge.backend
        model = state.default_model or "default"

        def generate_fn(prompt: str) -> str:
            """Sync wrapper: run backend.chat() in a new event loop thread."""
            async def _gen():
                msgs = [CM(role="user", content=prompt)]
                resp = await backend.chat(msgs, model, temperature=0)
                return resp.content
            # We're called from sync code inside an async handler;
            # use a fresh loop in a thread.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _gen())
                return future.result(timeout=120)

        auditor = state.stability_auditor
        result = auditor.probe(
            text, text, generate_fn,
            context=context,
            receipt_system=state.receipt_system,
            deep=deep,
        )
        return result.to_dict()

    dispatcher.register("stability.status", stability_status)
    dispatcher.register("stability.audit", stability_audit, mutating=True)
    dispatcher.register("stability.history", stability_history)
    dispatcher.register("stability.probe", stability_probe)

    # --- Lanes (capability-based routing) ---

    async def lanes_route(params: dict) -> dict:
        """Route a request to a lane + model. Returns RoutePlan."""
        lr = state.lane_router
        claims = None
        task_hint = params.get("task_hint")
        raw_claims = params.get("claims")
        if raw_claims:
            from .claims import Claim
            claims = [Claim.from_dict(c) if isinstance(c, dict) else c for c in raw_claims]
        plan = lr.route(
            claims=claims,
            task_hint=task_hint,
            risk_class=params.get("risk_class", "standard"),
            has_side_effects=params.get("has_side_effects", False),
            format_strict=params.get("format_strict", False),
            context_heavy=params.get("context_heavy", False),
            prompt_words=params.get("prompt_words", 0),
            must_have_strengths=params.get("must_have_strengths"),
            nice_to_have_strengths=params.get("nice_to_have_strengths"),
            force_lane=params.get("force_lane"),
        )
        return plan.to_dict()

    async def lanes_explain(params: dict) -> dict:
        """Explain a routing plan."""
        from .lanes import RoutePlan
        lr = state.lane_router
        plan_dict = params.get("plan")
        if not plan_dict:
            raise ValueError("Missing required param: plan")
        plan = RoutePlan.from_dict(plan_dict)
        return lr.explain(plan)

    async def lanes_status(params: dict) -> dict:
        """Return lane routing configuration status."""
        return state.lane_router.get_status()

    dispatcher.register("lanes.route", lanes_route, mutating=True)
    dispatcher.register("lanes.explain", lanes_explain)
    dispatcher.register("lanes.status", lanes_status)

    # --- Claims (claim↔receipt correlation) ---

    async def claims_list(params: dict) -> list:
        """List claims with verification status summaries. Newest first."""
        cs = state.claim_correlation_store
        run_id = params.get("run_id")
        since = params.get("since")
        limit = min(max(int(params.get("limit", 50)), 1), 500)
        claims = cs.list_claims(run_id=run_id, since=since, limit=limit)
        result = []
        for claim in claims:
            summary = cs.summarize(claim.claim_id, state.receipt_system)
            if summary:
                result.append(summary.to_dict())
        return result

    async def claims_detail(params: dict) -> dict:
        """Single claim + linked receipt stubs."""
        cs = state.claim_correlation_store
        claim_id = params.get("claim_id")
        if not claim_id:
            raise ValueError("Missing required param: claim_id")
        summary = cs.summarize(claim_id, state.receipt_system)
        if summary is None:
            raise ValueError(f"Claim not found: {claim_id}")
        links = cs.get_links(claim_id)
        # Build receipt stubs (no N+1 — bounded by link count)
        receipt_stubs = []
        for link in links:
            try:
                r = state.receipt_system.receipt_store.get_by_id(link.receipt_id)
                if r is not None:
                    receipt_stubs.append({
                        "receipt_id": r.receipt_id,
                        "timestamp": r.timestamp,
                        "verdict": r.verdict,
                        "gate": r.gate,
                    })
            except Exception:
                pass
        return {
            "summary": summary.to_dict(),
            "links": [l.to_dict() for l in links],
            "receipts": receipt_stubs,
        }

    async def claims_for_receipt(params: dict) -> list:
        """Which claims does a receipt relate to?"""
        cs = state.claim_correlation_store
        receipt_id = params.get("receipt_id")
        if not receipt_id:
            raise ValueError("Missing required param: receipt_id")
        claims = cs.get_claims_for_receipt(receipt_id)
        result = []
        for claim in claims:
            summary = cs.summarize(claim.claim_id, state.receipt_system)
            if summary:
                result.append(summary.to_dict())
        return result

    async def claims_window(params: dict) -> dict:
        """Time-window bundle for Guvnah timeline."""
        cs = state.claim_correlation_store
        since = params.get("since")
        if not since:
            raise ValueError("Missing required param: since")
        until = params.get("until")
        limit = min(max(int(params.get("limit", 50)), 1), 500)
        result = cs.window(
            since=since, until=until,
            receipt_system=state.receipt_system, limit=limit,
        )
        return result.to_dict()

    async def claims_stats(params: dict) -> dict:
        """Quick rollup for top-card."""
        return state.claim_correlation_store.stats()

    dispatcher.register("claims.list", claims_list)
    dispatcher.register("claims.detail", claims_detail)
    dispatcher.register("claims.for_receipt", claims_for_receipt)
    dispatcher.register("claims.window", claims_window)
    dispatcher.register("claims.stats", claims_stats)

    # --- Policy Engine ---

    async def policy_evaluate(params: dict) -> dict:
        """Evaluate a request against the loaded policy rule set.

        Params:
            request (dict, required): PolicyEvalRequest as dict.
            strict_taxonomy (bool|str, default True): If True, unknown
                capabilities cause immediate BLOCK.

        Returns PolicyEvalResult as dict. Emits a gate receipt.
        """
        from .policy_engine import (
            PolicyEvalRequest as PER,
            evaluate,
            request_content_hash,
            POLICY_ENGINE_VERSION,
        )

        raw_request = params.get("request")
        if not raw_request:
            raise ValueError("Missing required param: request")

        # Coerce strict_taxonomy: accept bool or "true"/"false" strings
        raw_strict = params.get("strict_taxonomy", True)
        if isinstance(raw_strict, bool):
            strict_taxonomy = raw_strict
        elif isinstance(raw_strict, str):
            lower = raw_strict.strip().lower()
            if lower == "true":
                strict_taxonomy = True
            elif lower == "false":
                strict_taxonomy = False
            else:
                raise ValueError(
                    f"strict_taxonomy must be true/false, got: {raw_strict!r}"
                )
        else:
            raise ValueError(
                f"strict_taxonomy must be bool or string, got: {type(raw_strict).__name__}"
            )

        request = PER.from_dict(raw_request)
        t0 = time.monotonic()
        result = evaluate(request, state.policy_rule_set, strict_taxonomy=strict_taxonomy)
        duration_ms = round((time.monotonic() - t0) * 1000, 2)

        # Emit gate receipt with bounded payload
        try:
            state.receipt_system.emit(
                gate="policy_engine",
                verdict=result.verdict.value,
                subject_kind="policy_eval_request",
                subject_bytes=request_content_hash(request).encode("utf-8"),
                evidence_bundle={
                    # Canonical fragment fields (same shape as gate fragments)
                    "matched_rule_ids": [r.rule_id for r in result.matched_rules],
                    "obligation_kinds": [o.kind for o in result.obligations],
                    "policy_identity": result.policy_identity.to_dict(),
                    "applied": True,
                    "duration_ms": duration_ms,
                    # RPC-specific context (not in gate fragments)
                    "request_id": request.request_id,
                    "reason_codes": list(result.rationale.reason_codes),
                },
                gate_config={
                    "strict_taxonomy": strict_taxonomy,
                    "policy_engine_version": POLICY_ENGINE_VERSION,
                },
            )
        except Exception:
            logger.warning(
                "receipt_emit_failed: policy_engine gate receipt not written",
                exc_info=True,
            )

        return result.to_dict()

    async def policy_info(params: dict) -> dict:
        """Return policy metadata.

        Policy is loaded lazily and cached for daemon lifetime (no auto-reload).
        """
        from .policy_engine import POLICY_ENGINE_VERSION
        rs = state.policy_rule_set  # triggers lazy load if needed
        return {
            "source": "file" if state._policy_load_status == "loaded" else "default",
            "load_status": state._policy_load_status,
            "policy_bundle_id": rs.policy_bundle_id,
            "policy_bundle_version": rs.policy_bundle_version,
            "rule_count": len(rs.rules),
            "default_verdict": rs.default_verdict,
            "description": rs.description,
            "capability_vocab_version": rs.capability_vocab_version,
            "obligation_vocab_version": rs.obligation_vocab_version,
            "policy_engine_version": POLICY_ENGINE_VERSION,
            "policy_content_hash": state._policy_content_hash,
            "loaded_at": state._policy_loaded_at,
        }

    async def policy_capabilities(params: dict) -> dict:
        """Return the capability and obligation vocabularies."""
        from .policy_engine import (
            Capability,
            ObligationKind,
            CAPABILITY_VOCAB_VERSION,
            OBLIGATION_VOCAB_VERSION,
            POLICY_ENGINE_VERSION,
        )
        return {
            "policy_engine_version": POLICY_ENGINE_VERSION,
            "capability_vocab_version": CAPABILITY_VOCAB_VERSION,
            "obligation_vocab_version": OBLIGATION_VOCAB_VERSION,
            "capabilities": [c.value for c in Capability],
            "obligations": [o.value for o in ObligationKind],
        }

    dispatcher.register("policy.evaluate", policy_evaluate)
    dispatcher.register("policy.info", policy_info)
    dispatcher.register("policy.capabilities", policy_capabilities)

    # --- Chain Composition Gate (Phase 2B: detect-only) ---

    async def chain_evaluate(params: dict) -> dict:
        """Evaluate a tool action against composition rules (2B compat shim).

        DEPRECATED in Phase 2C — use chain.preflight + chain.record instead.
        Only available in detect_only mode; returns structured error otherwise.

        Server-owned annotation: daemon calls annotate_step() to build
        the ActionStep. Caller supplies tool_id + args + result_status;
        classification fields are ignored (trust boundary).

        Persists action log, emits gate receipt, returns ChainEvalResult.
        """
        from .chain_gate import (
            ChainGate,
            ChainMode,
            ActionLog,
            annotate_step as _annotate_step,
            compute_action_log_hash,
        )
        from .gate_receipt import canonical_json as _cj

        # Phase 2C: restrict to detect_only mode
        if state.chain_mode != ChainMode.DETECT_ONLY.value:
            return {
                "error": "not_allowed_in_mode",
                "message": (
                    f"chain.evaluate is only supported in detect_only mode "
                    f"(current: {state.chain_mode}); "
                    f"use chain.preflight + chain.record"
                ),
                "mode": state.chain_mode,
            }

        tool_id = params.get("tool_id")
        if not tool_id:
            raise TypeError("tool_id is required")
        correlation_id = params.get("correlation_id")
        if not correlation_id:
            raise TypeError("correlation_id is required")

        args = params.get("args") or {}
        result_status = params.get("result_status", "ok")
        exceptions = set(params.get("exceptions", []))

        # Server-owned annotation
        proposed_step = _annotate_step(tool_id, args, result_status)

        # Load or create action log
        action_log = state.chain_action_logs.get(correlation_id)
        if action_log is None:
            action_log = ActionLog(
                correlation_id=correlation_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        # Pure evaluation
        gate = ChainGate()
        result = gate.evaluate(
            action_log,
            proposed_step,
            state.chain_rule_set,
            exceptions=exceptions,
            policy=state.policy_rule_set,
        )

        # Append proposed step + persist BEFORE receipt emission
        action_log.append(proposed_step)

        # Dedupe: record matches and determine receipt style
        dedupe_info: list[dict[str, Any]] = []
        for dk in result.dedupe_keys:
            count = action_log.record_match(dk)
            dedupe_info.append({
                "key": dk,
                "count": count,
                "is_repeat": count > 1,
            })

        state.chain_action_logs.put(action_log)

        # Receipt emission (daemon owns this, not ChainGate)
        verdict_map = {"deny": "block", "allow": "pass"}
        receipt_verdict = verdict_map.get(result.effective_verdict, "pass")

        evidence_bundle: dict[str, Any] = {
            "action_log_hash": result.action_log_hash,
            "proposed_step": result.proposed_step_dict,
            "matched_rule_ids": result.matched_rule_ids,
            "exception_results": result.exception_results,
            "history_length": result.history_length,
            "mode": result.mode,
            "correlation_id": correlation_id,
            "verdict_reason": result.verdict_reason,
            "dedupe_counts": dict(action_log.dedupe_counts),
        }
        if result.policy_fragment is not None:
            evidence_bundle["policy_fragment"] = result.policy_fragment

        gate_config: dict[str, Any] = {
            "load_status": state._chain_load_status,
            "rule_count": len(state.chain_rule_set.rules),
            "mode": state.chain_mode,
            "correlation_id": correlation_id,
        }

        try:
            state.receipt_system.emit(
                gate="chain_composition",
                verdict=receipt_verdict,
                subject_kind="action_sequence",
                subject_bytes=result.action_log_bytes,
                evidence_bundle=evidence_bundle,
                gate_config=gate_config,
            )
        except Exception:
            logger.warning(
                "receipt_suppressed: chain_composition gate receipt not written",
                exc_info=True,
            )

        resp = result.to_dict()
        resp["dedupe"] = dedupe_info
        resp["deprecated"] = True
        resp["replacement"] = ["chain.preflight", "chain.record"]
        return resp

    # ------------------------------------------------------------------
    # chain.preflight — Phase 2C pre-dispatch evaluation (mutates dedupe)
    # ------------------------------------------------------------------

    async def chain_preflight(params: dict) -> dict:
        """Pre-dispatch composition evaluation.

        Evaluates proposed tool action against composition rules and returns
        a mode-aware decision (allow/would_block/blocked), block reasons,
        and a CAS binding token for chain.record validation.

        Mutates dedupe counts (not the step log).

        Params:
            tool_id (str): required
            correlation_id (str): required
            args (dict): optional
            exceptions (list[str]): optional
        """
        from .chain_gate import (
            ChainGate,
            ChainMode,
            ActionLog,
            annotate_step as _annotate_step,
            compute_action_log_hash,
        )
        from .gate_receipt import canonical_json as _cj

        tool_id = params.get("tool_id")
        if not tool_id:
            raise TypeError("tool_id is required")
        correlation_id = params.get("correlation_id")
        if not correlation_id:
            raise TypeError("correlation_id is required")

        args = params.get("args") or {}
        exceptions = set(params.get("exceptions", []))

        # Server-owned annotation (always result_status="ok" for preflight)
        proposed_step = _annotate_step(tool_id, args, result_status="ok")

        # Load or create action log (no step mutation)
        action_log = state.chain_action_logs.get(correlation_id)
        if action_log is None:
            action_log = ActionLog(
                correlation_id=correlation_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        # Pure evaluation
        mode = ChainMode(state.chain_mode)
        gate = ChainGate()
        result = gate.preflight(
            action_log,
            proposed_step,
            state.chain_rule_set,
            mode=mode,
            exceptions=exceptions,
            policy=state.policy_rule_set,
        )

        # Dedupe: preflight owns dedupe counts for preflight receipts
        dedupe_info: dict[str, Any] = {}
        for rule_id, dk in result.dedupe_candidates.items():
            count = action_log.record_match(dk)
            dedupe_info[rule_id] = {"key": dk, "count": count}

        # Persist dedupe changes (but NOT step append)
        state.chain_action_logs.put(action_log)

        # Receipt emission
        decision_verdict_map = {
            "allow": "pass",
            "would_block": "warn",
            "blocked": "block",
        }
        receipt_verdict = decision_verdict_map.get(result.decision, "pass")

        rs = state.chain_rule_set
        evidence_bundle: dict[str, Any] = {
            "schema_version": "chain-preflight-receipt-v1",
            "decision": result.decision,
            "mode": result.mode,
            "kernel_verdict": result.kernel_verdict,
            "effective_verdict": result.effective_verdict,
            "composition_match": result.composition_match,
            "verdict_reason": result.verdict_reason,
            "history_length": result.history_length,
            "action_log_hash": result.action_log_hash,
            "proposed_step": result.proposed_step_dict,
            "matched_rule_ids": result.matched_rule_ids,
            "exception_results": result.exception_results,
            "block_reasons": result.block_reasons,
            "preflight_token": result.preflight_token,
            "dedupe": {
                "candidates": result.dedupe_candidates,
                "counts": dict(action_log.dedupe_counts),
            },
            "correlation_id": correlation_id,
        }
        if result.policy_fragment is not None:
            evidence_bundle["policy_fragment"] = result.policy_fragment

        gate_config: dict[str, Any] = {
            "schema_version": "chain-preflight-config-v1",
            "mode": state.chain_mode,
            "chain_rules": {
                "load_status": state._chain_load_status,
                "rule_count": len(rs.rules),
                "rule_set_version": rs.rule_set_version,
                "content_hash": state._chain_content_hash,
            },
        }
        if state._policy_rule_set is not None:
            gate_config["policy"] = {
                "load_status": state._policy_load_status,
                "bundle_id": getattr(state._policy_rule_set, "policy_bundle_id", None),
                "bundle_version": getattr(state._policy_rule_set, "policy_bundle_version", None),
            }

        try:
            state.receipt_system.emit(
                gate="chain_composition",
                verdict=receipt_verdict,
                subject_kind="action_sequence",
                subject_bytes=result.action_log_bytes,
                evidence_bundle=evidence_bundle,
                gate_config=gate_config,
            )
        except Exception:
            logger.warning(
                "receipt_suppressed: chain_composition preflight receipt not written",
                exc_info=True,
            )

        resp = result.to_dict()
        resp["dedupe"] = dedupe_info
        resp["correlation_id"] = correlation_id
        return resp

    # ------------------------------------------------------------------
    # chain.record — Phase 2C post-dispatch recording (mutates step log)
    # ------------------------------------------------------------------

    async def chain_record(params: dict) -> dict:
        """Record a completed tool action in the action log.

        Appends the step to the action log.  Optionally validates a
        preflight CAS token to prevent TOCTOU drift.  Supports
        idempotent recording via record_id.

        Params:
            tool_id (str): required
            correlation_id (str): required
            result_status (str): required ("ok" | "failed" | "timeout")
            args (dict): optional
            preflight_token (str): optional — CAS binding from chain.preflight
            record_id (str): optional — idempotency key
        """
        from .chain_gate import (
            ActionLog,
            annotate_step as _annotate_step,
            compute_action_log_hash,
            compute_preflight_token,
            compute_proposed_step_hash,
        )
        from .gate_receipt import canonical_json as _cj

        tool_id = params.get("tool_id")
        if not tool_id:
            raise TypeError("tool_id is required")
        correlation_id = params.get("correlation_id")
        if not correlation_id:
            raise TypeError("correlation_id is required")
        result_status = params.get("result_status")
        if not result_status:
            raise TypeError("result_status is required")
        if result_status not in ("ok", "failed", "timeout"):
            raise TypeError(
                f"result_status must be ok/failed/timeout, got '{result_status}'"
            )

        args = params.get("args") or {}
        preflight_token = params.get("preflight_token")
        record_id = params.get("record_id")

        # Load or create action log
        action_log = state.chain_action_logs.get(correlation_id)
        if action_log is None:
            action_log = ActionLog(
                correlation_id=correlation_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        # Idempotency check
        if record_id and record_id in action_log.seen_record_ids:
            return {
                "recorded": True,
                "correlation_id": correlation_id,
                "history_length": len(action_log.steps),
                "record_id": record_id,
                "idempotent_replay": True,
            }

        # CAS binding validation
        if preflight_token:
            # Build proposed step to get its stable hash
            proposed_step = _annotate_step(tool_id, args, result_status)
            proposed_step_hash = compute_proposed_step_hash(
                proposed_step.to_dict()
            )

            # Preflight computed token over (steps + proposed_step) hash
            all_steps = list(action_log.steps) + [proposed_step]
            _, expected_log_hash = compute_action_log_hash(all_steps)
            expected_token = compute_preflight_token(
                expected_log_hash, proposed_step_hash,
            )

            if preflight_token != expected_token:
                return {
                    "error": "stale_preflight",
                    "message": (
                        "Preflight token does not match current state. "
                        "The action log or proposed step may have changed "
                        "since preflight was called."
                    ),
                    "correlation_id": correlation_id,
                }

        # Server-owned annotation
        proposed_step = _annotate_step(tool_id, args, result_status)

        # Append step + persist
        action_log.append(proposed_step)
        if record_id:
            action_log.seen_record_ids.add(record_id)
        state.chain_action_logs.put(action_log)

        # Post-append hash
        _, post_hash = compute_action_log_hash(action_log.steps)

        recorded_step = proposed_step.to_dict()

        # Emit record receipt
        try:
            subject_bytes = _cj({
                "correlation_id": correlation_id,
                "steps": [s.to_dict() for s in action_log.steps],
            })
            state.receipt_system.emit(
                gate="chain_composition",
                verdict="pass",
                subject_kind="action_sequence",
                subject_bytes=subject_bytes,
                evidence_bundle={
                    "schema_version": "chain-record-receipt-v1",
                    "correlation_id": correlation_id,
                    "event": "step_recorded",
                    "history_length": len(action_log.steps),
                    "action_log_hash": post_hash,
                    "recorded_step": recorded_step,
                    "record_id": record_id,
                    "preflight_token_validated": preflight_token is not None,
                },
                gate_config={
                    "schema_version": "chain-record-config-v1",
                    "mode": state.chain_mode,
                },
            )
        except Exception:
            logger.warning(
                "receipt_suppressed: chain_composition record receipt not written",
                exc_info=True,
            )

        return {
            "recorded": True,
            "correlation_id": correlation_id,
            "history_length": len(action_log.steps),
            "recorded_step": recorded_step,
            "action_log_hash": post_hash,
            "record_id": record_id,
        }

    async def chain_status(params: dict) -> dict:
        """Return chain gate status.  Optionally include action log info."""
        # Trigger lazy load of rules
        rs = state.chain_rule_set
        result: dict[str, Any] = {
            "load_status": state._chain_load_status,
            "rule_count": len(rs.rules),
            "rule_set_version": rs.rule_set_version,
            "content_hash": state._chain_content_hash,
            "loaded_at": state._chain_loaded_at,
            "mode": state.chain_mode,
        }

        correlation_id = params.get("correlation_id")
        if correlation_id:
            log = state.chain_action_logs.get(correlation_id)
            if log is not None:
                from .chain_gate import compute_action_log_hash
                _, log_hash = compute_action_log_hash(log.steps)
                result["log_exists"] = True
                result["history_length"] = len(log.steps)
                result["action_log_hash"] = log_hash
            else:
                result["log_exists"] = False
                result["history_length"] = 0
                result["action_log_hash"] = None

        return result

    async def chain_rules(params: dict) -> dict:
        """Return loaded chain composition rules."""
        rs = state.chain_rule_set
        return {
            "load_status": state._chain_load_status,
            "rule_set_version": rs.rule_set_version,
            "rule_count": len(rs.rules),
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "description": r.description,
                    "effect": r.effect,
                    "prior_sensitivity_gte": (
                        r.prior_sensitivity_gte.value
                        if r.prior_sensitivity_gte else None
                    ),
                    "prior_capability": (
                        r.prior_capability.value if r.prior_capability else None
                    ),
                    "prior_trust_domain": (
                        r.prior_trust_domain.value if r.prior_trust_domain else None
                    ),
                    "proposed_capability": (
                        r.proposed_capability.value if r.proposed_capability else None
                    ),
                    "proposed_trust_domain": (
                        r.proposed_trust_domain.value
                        if r.proposed_trust_domain else None
                    ),
                    "unless_condition": r.unless_condition,
                }
                for r in rs.rules
            ],
        }

    async def chain_reset(params: dict) -> dict:
        """Reset the action log for a correlation_id."""
        from .gate_receipt import canonical_json as _cj
        from .chain_gate import compute_action_log_hash

        correlation_id = params.get("correlation_id")
        if not correlation_id:
            raise TypeError("correlation_id is required")

        # Get previous state before reset
        prev_log = state.chain_action_logs.get(correlation_id)
        prev_length = len(prev_log.steps) if prev_log else 0
        log_existed = prev_log is not None
        prev_hash = None
        if prev_log and prev_log.steps:
            _, prev_hash = compute_action_log_hash(prev_log.steps)

        state.chain_action_logs.reset(correlation_id)

        # Emit reset receipt
        try:
            subject_bytes = _cj({
                "correlation_id": correlation_id,
                "reset": True,
            })
            evidence: dict[str, Any] = {
                "schema_version": "chain-reset-receipt-v1",
                "correlation_id": correlation_id,
                "previous_history_length": prev_length,
                "log_existed": log_existed,
                "verdict_reason": "explicit_reset",
            }
            if prev_hash is not None:
                evidence["previous_action_log_hash"] = prev_hash

            state.receipt_system.emit(
                gate="chain_composition",
                verdict="pass",
                subject_kind="action_sequence",
                subject_bytes=subject_bytes,
                evidence_bundle=evidence,
                gate_config={
                    "load_status": state._chain_load_status,
                    "rule_count": len(state.chain_rule_set.rules),
                    "mode": state.chain_mode,
                    "correlation_id": correlation_id,
                },
                receipt_role="reset",
            )
        except Exception:
            logger.warning(
                "receipt_suppressed: chain_composition reset receipt not written",
                exc_info=True,
            )

        return {
            "reset": True,
            "correlation_id": correlation_id,
            "previous_history_length": prev_length,
            "log_existed": log_existed,
        }

    dispatcher.register("chain.evaluate", chain_evaluate, mutating=True)
    dispatcher.register("chain.preflight", chain_preflight, mutating=True)
    dispatcher.register("chain.record", chain_record, mutating=True)
    dispatcher.register("chain.status", chain_status)
    dispatcher.register("chain.rules", chain_rules)
    dispatcher.register("chain.reset", chain_reset, mutating=True)

    dispatcher.register("chat.send", chat_send, mutating=True)
    dispatcher.register_streaming("chat.stream", chat_stream, mutating=True)
    dispatcher.register("chat.models", chat_models)
    dispatcher.register("chat.backend", chat_backend)

    # --- Signals (Signal Plane v1) ---

    async def signals_query(params: dict) -> dict:
        """Query instrumentation signals with filters."""
        store = state.signal_store
        rows = store.query(
            signal_name=params.get("signal_name"),
            phase=params.get("phase"),
            quality=params.get("quality"),
            session_id=params.get("session_id"),
            since=params.get("since"),
            until=params.get("until"),
            limit=params.get("limit", 50),
            after_seq=params.get("after_seq"),
        )
        limit = params.get("limit", 50)
        truncated = len(rows) > limit
        if truncated:
            rows = rows[:limit]
        return {"signals": rows, "count": len(rows), "truncated": truncated}

    async def signals_get(params: dict) -> dict:
        """Get a single signal by hash."""
        signal_hash = params.get("signal_hash")
        if not signal_hash:
            raise ValueError("signal_hash is required")
        store = state.signal_store
        row = store.get(signal_hash)
        if row is None:
            raise ValueError(f"Signal not found: {signal_hash}")
        return row

    async def signals_tail(params: dict) -> dict:
        """Tail recent signals."""
        store = state.signal_store
        limit = params.get("limit", 20)
        after_seq = params.get("after_seq")
        signal_name = params.get("signal_name")
        rows = store.tail(limit=limit, after_seq=after_seq, signal_name=signal_name)
        return {"signals": rows, "count": len(rows), "has_more": len(rows) >= limit}

    async def signals_stats(params: dict) -> dict:
        """Signal index statistics and ingest health."""
        store = state.signal_store
        jsonl_path = state.governor_dir / "signals" / "signals.jsonl"
        return store.stats(jsonl_path=jsonl_path if jsonl_path.exists() else None)

    async def signals_preflight(params: dict) -> dict:
        """Predict regime from latest signal envelopes in JSONL."""
        from .signal_store import load_latest_envelopes
        from .signals.predict_regime import predict_regime_preflight

        all_expected = [
            "EXPOSURE_PROXY", "SILENT_SUPPRESSION", "SIGMA_RATE",
            "CAPTURE_SELF_DIAGNOSTIC", "DECISION_EVIDENCE_LAG",
            "POSTERIOR_SHIFT_ATTRIBUTION",
        ]

        jsonl_path = state.governor_dir / "signals" / "signals.jsonl"
        envelopes = load_latest_envelopes(jsonl_path, all_expected)

        envelope = predict_regime_preflight(
            list(envelopes.values()),
            session_id=state.session_id,
        )

        return {
            "ok": True,
            "envelope": envelope.to_dict(),
            "inputs": len(envelopes),
        }

    dispatcher.register("signals.query", signals_query)
    dispatcher.register("signals.get", signals_get)
    dispatcher.register("signals.tail", signals_tail)
    dispatcher.register("signals.stats", signals_stats)
    dispatcher.register("signals.preflight", signals_preflight)

    # --- Runtime Supervisor ---

    async def runtime_session_create(params: dict) -> dict:
        """Create a supervised session (does not launch yet)."""
        backend_kind = params.get("backend_kind", "claude_code")
        cwd = params.get("cwd", str(state.root))
        task = params.get("task")
        operator_mode = params.get("operator_mode", "interactive")

        if backend_kind == "claude_code":
            from .runtime.adapters.claude_code import ClaudeCodeAdapter
            adapter = ClaudeCodeAdapter()
        elif backend_kind == "gemini_cli":
            from .runtime.adapters.gemini_cli import GeminiCliAdapter
            adapter = GeminiCliAdapter()
        else:
            raise ValueError(f"Unknown backend_kind: {backend_kind}")

        sup = state.runtime_supervisor
        record = sup.create_session(
            adapter=adapter,
            backend_kind=backend_kind,
            cwd=cwd,
            task=task,
            operator_mode=operator_mode,
        )
        return {
            "session_id": record.session_id,
            "backend_kind": record.backend_kind,
            "cwd": record.cwd,
            "status": record.status.value,
            "task": record.task,
        }

    async def runtime_session_launch(params: dict) -> dict:
        """Launch the backend for a created session."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        record = await asyncio.to_thread(sup.launch_session, session_id)
        return {
            "session_id": record.session_id,
            "status": record.status.value,
            "pid": record.pid,
        }

    async def runtime_session_get(params: dict) -> dict | None:
        """Get session details."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        record = sup.get_session(session_id)
        if not record:
            return None
        return {
            "session_id": record.session_id,
            "backend_kind": record.backend_kind,
            "cwd": record.cwd,
            "status": record.status.value,
            "pid": record.pid,
            "task": record.task,
            "started_at": record.started_at,
            "updated_at": record.updated_at,
            "exit_code": record.exit_code,
            "pending_interventions": len(sup.get_pending_interventions(session_id)),
        }

    async def runtime_session_list(params: dict) -> list:
        """List all sessions."""
        sup = state.runtime_supervisor
        sessions = sup.list_sessions()
        return [
            {
                "session_id": s.session_id,
                "backend_kind": s.backend_kind,
                "status": s.status.value,
                "task": s.task,
                "pid": s.pid,
                "started_at": s.started_at,
                "updated_at": s.updated_at,
                "parent_session_id": s.parent_session_id,
                "pending_interventions": len(sup.get_pending_interventions(s.session_id)),
            }
            for s in sessions
        ]

    async def runtime_session_events(params: dict) -> list:
        """Get canonical events for a session."""
        session_id = params["session_id"]
        since_seq = int(params.get("since_seq", 0))
        limit = min(int(params.get("limit", 100)), 1000)
        sup = state.runtime_supervisor
        events = sup.get_events(session_id, since_seq=since_seq, limit=limit)
        return [e.to_dict() for e in events]

    async def runtime_session_pause(params: dict) -> dict:
        """Soft pause a session."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        record = sup.pause_session(session_id)
        return {"session_id": record.session_id, "status": record.status.value}

    async def runtime_session_resume(params: dict) -> dict:
        """Resume a paused session."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        record = sup.resume_session(session_id)
        return {"session_id": record.session_id, "status": record.status.value}

    async def runtime_session_kill(params: dict) -> dict:
        """Kill a session."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        record = sup.kill_session(session_id)
        return {"session_id": record.session_id, "status": record.status.value}

    async def runtime_intervention_list(params: dict) -> list:
        """List pending interventions for a session."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        interventions = sup.get_pending_interventions(session_id)
        return [
            {
                "intervention_id": i.intervention_id,
                "tool_call_id": i.tool_call_id,
                "tool_name": i.tool_name,
                "tool_input": i.tool_input,
                "elapsed_seconds": round(i.elapsed, 1),
                "remaining_seconds": round(i.remaining, 1),
                "timed_out": i.timed_out,
            }
            for i in interventions
        ]

    async def runtime_intervention_resolve(params: dict) -> dict:
        """Resolve a pending intervention (approve/deny)."""
        session_id = params["session_id"]
        tool_call_id = params["tool_call_id"]
        decision = params["decision"]  # "approve" or "deny"
        reason = params.get("reason")
        sup = state.runtime_supervisor
        result = sup.resolve_intervention(session_id, tool_call_id, decision, reason=reason)
        if not result:
            return {"resolved": False, "error": "No pending intervention for tool_call_id"}
        return {
            "resolved": True,
            "intervention_id": result.intervention_id,
            "decision": result.decision,
        }

    dispatcher.register("runtime.session.create", runtime_session_create, mutating=True)
    dispatcher.register("runtime.session.launch", runtime_session_launch, mutating=True)
    dispatcher.register("runtime.session.get", runtime_session_get)
    dispatcher.register("runtime.session.list", runtime_session_list)
    dispatcher.register("runtime.session.events", runtime_session_events)
    dispatcher.register("runtime.session.pause", runtime_session_pause, mutating=True)
    dispatcher.register("runtime.session.resume", runtime_session_resume, mutating=True)
    async def runtime_session_fork(params: dict) -> dict:
        """Fork a new session from a promoted prior session."""
        parent_id = params["parent_session_id"]
        task = params.get("task")
        backend_kind = params.get("backend_kind", "claude_code")

        if backend_kind == "claude_code":
            from .runtime.adapters.claude_code import ClaudeCodeAdapter
            adapter = ClaudeCodeAdapter()
        elif backend_kind == "gemini_cli":
            from .runtime.adapters.gemini_cli import GeminiCliAdapter
            adapter = GeminiCliAdapter()
        else:
            raise ValueError(f"Unknown backend_kind: {backend_kind}")

        sup = state.runtime_supervisor
        record = sup.fork_session(parent_id, adapter, task=task)
        return {
            "session_id": record.session_id,
            "parent_session_id": record.parent_session_id,
            "status": record.status.value,
            "cwd": record.cwd,
            "task": record.task,
        }

    dispatcher.register("runtime.session.kill", runtime_session_kill, mutating=True)
    dispatcher.register("runtime.session.fork", runtime_session_fork, mutating=True)
    dispatcher.register("runtime.intervention.list", runtime_intervention_list)
    dispatcher.register("runtime.intervention.resolve", runtime_intervention_resolve, mutating=True)

    async def runtime_promotion_get(params: dict) -> dict | None:
        """Get pending promotion for a session."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        p = sup.get_pending_promotion(session_id)
        if not p:
            return None
        return p.to_dict()

    async def runtime_promotion_diff(params: dict) -> dict:
        """Get the diff text for a session's pending promotion."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        p = sup.get_pending_promotion(session_id)
        if not p:
            return {"error": "No pending promotion"}
        return {"promotion_id": p.promotion_id, "diff": p.diff_text}

    async def runtime_promotion_resolve(params: dict) -> dict:
        """Approve or reject a pending promotion."""
        session_id = params["session_id"]
        decision = params["decision"]  # "approve" or "reject"
        reason = params.get("reason")
        sup = state.runtime_supervisor
        p = sup.resolve_promotion(session_id, decision, reason=reason)
        if not p:
            return {"resolved": False, "error": "No pending promotion"}
        return {"resolved": True, "promotion_id": p.promotion_id, "status": p.status}

    dispatcher.register("runtime.promotion.get", runtime_promotion_get)
    dispatcher.register("runtime.promotion.diff", runtime_promotion_diff)
    dispatcher.register("runtime.promotion.resolve", runtime_promotion_resolve, mutating=True)

    async def runtime_budget_get(params: dict) -> dict | None:
        """Get budget status for a session."""
        session_id = params["session_id"]
        sup = state.runtime_supervisor
        return sup.get_budget(session_id)

    dispatcher.register("runtime.budget.get", runtime_budget_get)


# =============================================================================
# Server entry points
# =============================================================================


def _allow_mutating_from_config(state: DaemonState) -> bool:
    """Read allow_mutating_rpc from daemon config. Defaults to True (trusted local)."""
    val = state.daemon_config.get("daemon.allow_mutating_rpc", "true").strip().lower()
    return val in ("1", "true", "yes")


async def serve_stdio(state: DaemonState) -> None:
    """Serve JSON-RPC over stdin/stdout. Electron child process mode."""
    dispatcher = Dispatcher(allow_mutating=_allow_mutating_from_config(state))
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
    dispatcher = Dispatcher(allow_mutating=_allow_mutating_from_config(state))
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
