"""
CLI Chat — Governed Conversational CLI with Backend Switching.

Thin CLI layer over existing ChatBridge and GovernorHooks. Provides
single-turn governed queries from the terminal and backend management.

Spec: CLI_CHAT_SPEC.md (Layer 3, Item #8 of AG2 build order)

Design principles:
- No daemon — single invocation, not long-running
- Pipe-friendly — prompt via stdin, response via stdout, violations via stderr
- No conversation memory — each call is a single turn
- Async under the hood — backends use async; CLI wraps in asyncio.run()
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Config — backend persistence
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path(".governor/chat_config.json")


@dataclass
class ChatConfig:
    """Persisted chat configuration."""

    active_backend: str = "ollama"
    active_model: str = ""
    backend_options: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_backend": self.active_backend,
            "active_model": self.active_model,
            "backend_options": self.backend_options,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChatConfig:
        return cls(
            active_backend=d.get("active_backend", "ollama"),
            active_model=d.get("active_model", ""),
            backend_options=d.get("backend_options", {}),
        )

    def save(self, path: Path | None = None) -> Path:
        p = path or DEFAULT_CONFIG_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return p

    @classmethod
    def load(cls, path: Path | None = None) -> ChatConfig:
        p = path or DEFAULT_CONFIG_PATH
        if not p.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(p.read_text()))
        except (json.JSONDecodeError, KeyError):
            return cls()


# ---------------------------------------------------------------------------
# Backend probing — availability detection
# ---------------------------------------------------------------------------

KNOWN_BACKENDS = ("ollama", "anthropic", "claude-code", "codex")

DEFAULT_MODELS: dict[str, str] = {
    "ollama": "llama3:latest",
    "anthropic": "claude-sonnet-4-20250514",
    "claude-code": "claude-sonnet-4-20250514",
    "codex": "codex-mini-latest",
}


@dataclass
class BackendInfo:
    """Information about a backend's availability."""

    name: str
    available: bool
    reason: str = ""
    models: list[str] = field(default_factory=list)
    default_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "reason": self.reason,
            "models": self.models,
            "default_model": self.default_model,
        }


def _check_ollama() -> BackendInfo:
    """Check if Ollama is available."""
    import subprocess

    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=3,
        )
        if r.stdout.strip() == "200":
            # Try to get model list
            try:
                r2 = subprocess.run(
                    ["curl", "-s", "http://localhost:11434/api/tags"],
                    capture_output=True, text=True, timeout=3,
                )
                data = json.loads(r2.stdout)
                models = [m["name"] for m in data.get("models", [])]
                default = models[0] if models else DEFAULT_MODELS["ollama"]
                return BackendInfo(
                    name="ollama", available=True,
                    reason=f"http://localhost:11434, {len(models)} models",
                    models=models, default_model=default,
                )
            except Exception:
                return BackendInfo(
                    name="ollama", available=True,
                    reason="http://localhost:11434",
                    default_model=DEFAULT_MODELS["ollama"],
                )
        return BackendInfo(name="ollama", available=False, reason="server not responding")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return BackendInfo(name="ollama", available=False, reason="server not reachable")


def _check_anthropic() -> BackendInfo:
    """Check if Anthropic API key is set."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return BackendInfo(
            name="anthropic", available=True,
            reason=f"API key set ({key[:8]}...)",
            default_model=DEFAULT_MODELS["anthropic"],
        )
    return BackendInfo(name="anthropic", available=False, reason="ANTHROPIC_API_KEY not set")


def _check_claude_code() -> BackendInfo:
    """Check if Claude Code CLI is available."""
    import shutil

    path = shutil.which("claude")
    if path:
        return BackendInfo(
            name="claude-code", available=True,
            reason=path,
            default_model=DEFAULT_MODELS["claude-code"],
        )
    return BackendInfo(name="claude-code", available=False, reason="claude not found in PATH")


def _check_codex() -> BackendInfo:
    """Check if Codex CLI is available."""
    import shutil

    path = shutil.which("codex")
    if path:
        return BackendInfo(
            name="codex", available=True,
            reason=path,
            default_model=DEFAULT_MODELS["codex"],
        )
    return BackendInfo(name="codex", available=False, reason="codex not found in PATH")


def probe_backends() -> list[BackendInfo]:
    """Probe all known backends for availability."""
    checkers = {
        "ollama": _check_ollama,
        "anthropic": _check_anthropic,
        "claude-code": _check_claude_code,
        "codex": _check_codex,
    }
    results = []
    for name in KNOWN_BACKENDS:
        try:
            results.append(checkers[name]())
        except Exception as e:
            results.append(BackendInfo(name=name, available=False, reason=str(e)))
    return results


def probe_backend(name: str) -> BackendInfo:
    """Probe a single backend."""
    checkers = {
        "ollama": _check_ollama,
        "anthropic": _check_anthropic,
        "claude-code": _check_claude_code,
        "codex": _check_codex,
    }
    if name not in checkers:
        return BackendInfo(name=name, available=False, reason=f"unknown backend: {name}")
    try:
        return checkers[name]()
    except Exception as e:
        return BackendInfo(name=name, available=False, reason=str(e))


# ---------------------------------------------------------------------------
# Chat result
# ---------------------------------------------------------------------------

@dataclass
class ChatResult:
    """Result of a governed chat invocation."""

    response: str
    model: str
    backend: str
    violations: list[dict[str, Any]] = field(default_factory=list)
    checked_anchors: int = 0
    passed: bool = True
    usage: dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "model": self.model,
            "backend": self.backend,
            "violations": self.violations,
            "checked_anchors": self.checked_anchors,
            "passed": self.passed,
            "usage": self.usage,
            "latency_ms": round(self.latency_ms, 1),
        }


# ---------------------------------------------------------------------------
# Core chat function
# ---------------------------------------------------------------------------

def _create_backend_instance(
    backend_name: str, config: ChatConfig
) -> Any:
    """Create a ChatBackend instance from name and config."""
    from .chat_bridge import create_backend

    opts = config.backend_options.get(backend_name, {})

    if backend_name == "ollama":
        return create_backend("ollama", host=opts.get("host", "http://localhost:11434"))
    elif backend_name == "anthropic":
        api_key = opts.get("api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set and no api_key in config")
        return create_backend("anthropic", api_key=api_key)
    elif backend_name == "claude-code":
        return create_backend("claude-code", claude_path=opts.get("path", "claude"))
    elif backend_name == "codex":
        return create_backend("codex", codex_path=opts.get("path", "codex"))
    else:
        raise ValueError(f"Unknown backend: {backend_name}")


def _resolve_model(
    backend_name: str, explicit_model: str, config: ChatConfig
) -> str:
    """Resolve which model to use."""
    if explicit_model:
        return explicit_model
    if config.active_model:
        return config.active_model
    return DEFAULT_MODELS.get(backend_name, "")


async def _run_chat_async(
    prompt: str,
    backend_name: str,
    model: str,
    config: ChatConfig,
    scope: str = "",
    mode: str = "code",
    use_hooks: bool = True,
) -> ChatResult:
    """Execute a single governed chat turn (async)."""
    from .chat_bridge import ChatMessage, GovernorHooks
    from .context_manager import GovernorContext

    start = time.monotonic()

    # Create backend
    backend = _create_backend_instance(backend_name, config)

    # Build messages
    messages = [ChatMessage(role="user", content=prompt)]

    # Apply governor hooks if enabled
    hooks = None
    if use_hooks:
        ctx = GovernorContext(
            context_id="cli-chat",
            mode=mode,
            root=Path.cwd(),
            governor_dir=Path.cwd() / ".governor",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            metadata={"scope": scope} if scope else {},
        )
        hooks = GovernorHooks(ctx)
        messages = hooks.augment_messages(messages)

    # Send to backend
    response = await backend.chat(messages, model)

    # Check response with governor hooks
    violations: list[dict[str, Any]] = []
    checked_anchors = 0
    passed = True
    if hooks:
        check_result = hooks.check_response_full(response.content)
        violations = check_result.violations
        checked_anchors = check_result.checked_anchors
        passed = check_result.passed

    latency_ms = (time.monotonic() - start) * 1000.0

    return ChatResult(
        response=response.content,
        model=response.model or model,
        backend=backend_name,
        violations=violations,
        checked_anchors=checked_anchors,
        passed=passed,
        usage=response.usage,
        latency_ms=latency_ms,
    )


def run_chat(
    prompt: str,
    backend: str = "",
    model: str = "",
    scope: str = "",
    mode: str = "code",
    use_hooks: bool = True,
    config_path: Path | None = None,
) -> ChatResult:
    """Execute a single governed chat turn (sync wrapper).

    Args:
        prompt: The user prompt
        backend: Backend name (or empty to use config default)
        model: Model name (or empty to use config/backend default)
        scope: File scope for constraint projection
        mode: Governor mode (code, fiction, nonfiction, general)
        use_hooks: Whether to apply governor hooks
        config_path: Path to chat config file

    Returns:
        ChatResult with response, violations, and metadata
    """
    config = ChatConfig.load(config_path)
    backend_name = backend or config.active_backend
    resolved_model = _resolve_model(backend_name, model, config)

    return asyncio.run(_run_chat_async(
        prompt=prompt,
        backend_name=backend_name,
        model=resolved_model,
        config=config,
        scope=scope,
        mode=mode,
        use_hooks=use_hooks,
    ))


# ---------------------------------------------------------------------------
# Compare — quick interferometry
# ---------------------------------------------------------------------------

@dataclass
class CompareResult:
    """Result of comparing two backend responses."""

    results: list[ChatResult]
    shared_signals: list[str] = field(default_factory=list)
    unique_signals: dict[str, list[str]] = field(default_factory=dict)
    conflict_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "shared_signals": self.shared_signals,
            "unique_signals": self.unique_signals,
            "conflict_signals": self.conflict_signals,
        }


def _extract_simple_signals(text: str) -> set[str]:
    """Extract simple claim signals from response text.

    Uses keyword-level extraction (not full SignalExtractor)
    for lightweight comparison.
    """
    signals: set[str] = set()
    lower = text.lower()

    # Action signals
    action_words = [
        "create", "delete", "modify", "add", "remove", "update",
        "refactor", "rename", "move", "install", "configure",
    ]
    for w in action_words:
        if w in lower:
            signals.add(f"action:{w}")

    # File references
    import re
    file_refs = re.findall(r'[\w/]+\.\w{1,5}', text)
    for f in file_refs:
        signals.add(f"file:{f}")

    # Code patterns
    if "```" in text:
        signals.add("contains:code_block")
    if "import " in text:
        signals.add("contains:import")
    if "def " in text or "function " in text:
        signals.add("contains:function_def")
    if "class " in text:
        signals.add("contains:class_def")

    # Commitment signals
    commitment_words = ["must", "should", "shall", "required", "necessary"]
    for w in commitment_words:
        if w in lower:
            signals.add(f"commitment:{w}")

    return signals


async def _run_compare_async(
    prompt: str,
    backends: list[tuple[str, str]],
    config: ChatConfig,
    scope: str = "",
    mode: str = "code",
) -> CompareResult:
    """Run prompt against multiple backends and compare."""
    # Run all backends concurrently
    tasks = []
    for backend_name, model_name in backends:
        resolved_model = _resolve_model(backend_name, model_name, config)
        tasks.append(_run_chat_async(
            prompt=prompt,
            backend_name=backend_name,
            model=resolved_model,
            config=config,
            scope=scope,
            mode=mode,
            use_hooks=True,
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions
    chat_results: list[ChatResult] = []
    for r in results:
        if isinstance(r, Exception):
            chat_results.append(ChatResult(
                response=f"Error: {r}",
                model="error",
                backend="error",
                passed=False,
            ))
        else:
            chat_results.append(r)

    # Compare signals
    all_signals: list[set[str]] = []
    for r in chat_results:
        all_signals.append(_extract_simple_signals(r.response))

    shared = set.intersection(*all_signals) if all_signals else set()
    unique: dict[str, list[str]] = {}
    for i, (bname, _) in enumerate(backends):
        if i < len(all_signals):
            u = all_signals[i] - shared
            if u:
                unique[bname] = sorted(u)

    # Conflicts: same category, different values across backends
    conflicts: list[str] = []
    if len(all_signals) >= 2:
        for i in range(len(all_signals)):
            for j in range(i + 1, len(all_signals)):
                # Find signals where category matches but value differs
                cats_i = {s.split(":")[0] for s in all_signals[i] if ":" in s}
                cats_j = {s.split(":")[0] for s in all_signals[j] if ":" in s}
                shared_cats = cats_i & cats_j
                for cat in shared_cats:
                    vals_i = {s for s in all_signals[i] if s.startswith(f"{cat}:")}
                    vals_j = {s for s in all_signals[j] if s.startswith(f"{cat}:")}
                    diff = vals_i.symmetric_difference(vals_j)
                    if diff:
                        conflicts.extend(sorted(diff))

    return CompareResult(
        results=chat_results,
        shared_signals=sorted(shared),
        unique_signals=unique,
        conflict_signals=sorted(set(conflicts)),
    )


def run_compare(
    prompt: str,
    backends: list[tuple[str, str]],
    scope: str = "",
    mode: str = "code",
    config_path: Path | None = None,
) -> CompareResult:
    """Compare prompt responses across multiple backends (sync wrapper).

    Args:
        prompt: The user prompt
        backends: List of (backend_name, model_name) tuples
        scope: File scope for constraint projection
        mode: Governor mode
        config_path: Path to chat config file

    Returns:
        CompareResult with responses and signal comparison
    """
    config = ChatConfig.load(config_path)
    return asyncio.run(_run_compare_async(
        prompt=prompt,
        backends=backends,
        config=config,
        scope=scope,
        mode=mode,
    ))


# ---------------------------------------------------------------------------
# Formatting — terminal output
# ---------------------------------------------------------------------------

def format_response(result: ChatResult, show_meta: bool = True) -> str:
    """Format a chat result for terminal output."""
    lines: list[str] = []
    lines.append(result.response)

    if show_meta:
        lines.append("")
        lines.append(f"--- [{result.backend}:{result.model}] "
                      f"{result.latency_ms:.0f}ms "
                      f"({result.usage.get('total_tokens', 0)} tokens) ---")

    if result.violations:
        lines.append("")
        lines.append(f"VIOLATIONS ({len(result.violations)}):")
        for v in result.violations:
            severity = v.get("severity", "unknown")
            anchor = v.get("anchor_id", v.get("anchor", "?"))
            desc = v.get("description", v.get("message", ""))
            lines.append(f"  [{severity}] {anchor}: {desc}")

    return "\n".join(lines)


def format_compare(result: CompareResult) -> str:
    """Format a compare result for terminal output."""
    lines: list[str] = []

    for i, r in enumerate(result.results):
        if i > 0:
            lines.append("")
            lines.append("=" * 60)
            lines.append("")

        label = f"[{r.backend}:{r.model}]"
        lines.append(label)
        lines.append("-" * len(label))
        lines.append(r.response)
        if r.violations:
            lines.append(f"\n  Violations: {len(r.violations)}")
            for v in r.violations:
                lines.append(f"    [{v.get('severity', '?')}] {v.get('anchor_id', '?')}")

    # Signal comparison
    lines.append("")
    lines.append("=" * 60)
    lines.append("Signal Comparison")
    lines.append("-" * 40)

    if result.shared_signals:
        lines.append(f"  Shared ({len(result.shared_signals)}): "
                      + ", ".join(result.shared_signals[:10]))
        if len(result.shared_signals) > 10:
            lines.append(f"    ... and {len(result.shared_signals) - 10} more")

    for backend, signals in result.unique_signals.items():
        lines.append(f"  Unique to {backend} ({len(signals)}): "
                      + ", ".join(signals[:10]))

    if result.conflict_signals:
        lines.append(f"  Conflicts ({len(result.conflict_signals)}): "
                      + ", ".join(result.conflict_signals[:10]))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parse backend spec strings
# ---------------------------------------------------------------------------

def parse_backend_spec(spec: str) -> tuple[str, str]:
    """Parse 'backend:model' or just 'backend' into (backend, model).

    Examples:
        'ollama:llama3' → ('ollama', 'llama3')
        'anthropic' → ('anthropic', '')
        'ollama:llama3:latest' → ('ollama', 'llama3:latest')
    """
    if ":" not in spec:
        return (spec, "")
    parts = spec.split(":", 1)
    backend = parts[0]
    model = parts[1] if len(parts) > 1 else ""
    return (backend, model)


def parse_backend_list(spec: str) -> list[tuple[str, str]]:
    """Parse comma-separated backend specs.

    Example: 'ollama:llama3,anthropic:claude-sonnet-4-20250514'
    """
    return [parse_backend_spec(s.strip()) for s in spec.split(",") if s.strip()]


# ---------------------------------------------------------------------------
# Telemetry event
# ---------------------------------------------------------------------------

def make_chat_event(result: ChatResult) -> dict[str, Any]:
    """Create a telemetry event from a chat result."""
    content_hash = hashlib.sha256(result.response.encode()).hexdigest()[:12]
    return {
        "type": "cli_chat",
        "backend": result.backend,
        "model": result.model,
        "response_hash": content_hash,
        "violations": len(result.violations),
        "checked_anchors": result.checked_anchors,
        "passed": result.passed,
        "latency_ms": round(result.latency_ms, 1),
        "tokens": result.usage.get("total_tokens", 0),
    }
