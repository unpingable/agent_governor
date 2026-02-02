"""
Structured telemetry: JSON-line logging, pluggable backends, cost/performance analysis.

Deferred 4, Phase B2: Observable telemetry for governor operations.
Logs to `.governor/logs/governor-YYYYMMDD.jsonl` with date-partitioned rotation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import traceback
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class TelemetryEventType(str, Enum):
    """Types of telemetry events."""

    PROPOSAL = "proposal"
    VERIFICATION = "verification"
    LLM_CALL = "llm_call"
    AUTONOMOUS_ITERATION = "autonomous_iteration"
    ERROR = "error"
    SECURITY_SCAN = "security_scan"
    CLAIM_REGISTERED = "claim_registered"
    PROFILE_CHANGE = "profile_change"


class TelemetryLevel(str, Enum):
    """Severity levels for telemetry events."""

    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


LEVEL_ORDER = {
    TelemetryLevel.DEBUG: 0,
    TelemetryLevel.INFO: 1,
    TelemetryLevel.WARN: 2,
    TelemetryLevel.ERROR: 3,
}


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class TelemetryConfig:
    """Telemetry configuration, stored in .governor/telemetry.json."""

    logging_enabled: bool = True
    log_dir: str = "logs"
    log_retention_days: int = 30
    log_max_size_mb: float = 50.0
    prometheus_enabled: bool = False  # B3 stub
    prometheus_port: int = 9090
    redact_file_contents: bool = True
    redact_prompts: bool = False
    min_level: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "logging_enabled": self.logging_enabled,
            "log_dir": self.log_dir,
            "log_retention_days": self.log_retention_days,
            "log_max_size_mb": self.log_max_size_mb,
            "prometheus_enabled": self.prometheus_enabled,
            "prometheus_port": self.prometheus_port,
            "redact_file_contents": self.redact_file_contents,
            "redact_prompts": self.redact_prompts,
            "min_level": self.min_level,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TelemetryConfig:
        return cls(
            logging_enabled=d.get("logging_enabled", True),
            log_dir=d.get("log_dir", "logs"),
            log_retention_days=d.get("log_retention_days", 30),
            log_max_size_mb=d.get("log_max_size_mb", 50.0),
            prometheus_enabled=d.get("prometheus_enabled", False),
            prometheus_port=d.get("prometheus_port", 9090),
            redact_file_contents=d.get("redact_file_contents", True),
            redact_prompts=d.get("redact_prompts", False),
            min_level=d.get("min_level", "info"),
        )

    def save(self, gov_dir: Path) -> None:
        path = gov_dir / "telemetry.json"
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, gov_dir: Path) -> TelemetryConfig:
        path = gov_dir / "telemetry.json"
        if path.exists():
            try:
                return cls.from_dict(json.loads(path.read_text()))
            except (json.JSONDecodeError, TypeError):
                return cls()
        return cls()

    @property
    def min_level_enum(self) -> TelemetryLevel:
        try:
            return TelemetryLevel(self.min_level)
        except ValueError:
            return TelemetryLevel.INFO


# =============================================================================
# Core Event
# =============================================================================


@dataclass
class TelemetryEvent:
    """A single telemetry event."""

    timestamp: str
    event_type: TelemetryEventType
    level: TelemetryLevel
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    fields: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    session_id: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value if isinstance(self.event_type, Enum) else self.event_type,
            "level": self.level.value if isinstance(self.level, Enum) else self.level,
            "event_id": self.event_id,
            "fields": self.fields,
        }
        if self.agent_id is not None:
            d["agent_id"] = self.agent_id
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TelemetryEvent:
        event_type = d.get("event_type", "error")
        if isinstance(event_type, str):
            try:
                event_type = TelemetryEventType(event_type)
            except ValueError:
                event_type = TelemetryEventType.ERROR

        level = d.get("level", "info")
        if isinstance(level, str):
            try:
                level = TelemetryLevel(level)
            except ValueError:
                level = TelemetryLevel.INFO

        return cls(
            timestamp=d.get("timestamp", ""),
            event_type=event_type,
            level=level,
            event_id=d.get("event_id", ""),
            fields=d.get("fields", {}),
            agent_id=d.get("agent_id"),
            session_id=d.get("session_id"),
            duration_ms=d.get("duration_ms"),
        )

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


# =============================================================================
# Field Helpers (build event fields dicts)
# =============================================================================


@dataclass
class ProposalFields:
    """Fields for a PROPOSAL event."""

    proposal_id: str
    claim_count: int = 0
    claim_types: list[str] = field(default_factory=list)
    envelope_mode: str = "strict"
    outcome: str = ""  # "proposed", "verified", "applied", "rejected"

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "claim_count": self.claim_count,
            "claim_types": self.claim_types,
            "envelope_mode": self.envelope_mode,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProposalFields:
        return cls(
            proposal_id=d.get("proposal_id", ""),
            claim_count=d.get("claim_count", 0),
            claim_types=d.get("claim_types", []),
            envelope_mode=d.get("envelope_mode", "strict"),
            outcome=d.get("outcome", ""),
        )


@dataclass
class VerificationFields:
    """Fields for a VERIFICATION event."""

    proposal_id: str
    claim_index: int = 0
    claim_type: str = ""
    success: bool = False
    error: str = ""
    receipt_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "claim_index": self.claim_index,
            "claim_type": self.claim_type,
            "success": self.success,
            "error": self.error,
            "receipt_type": self.receipt_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VerificationFields:
        return cls(
            proposal_id=d.get("proposal_id", ""),
            claim_index=d.get("claim_index", 0),
            claim_type=d.get("claim_type", ""),
            success=d.get("success", False),
            error=d.get("error", ""),
            receipt_type=d.get("receipt_type", ""),
        )


@dataclass
class LLMCallFields:
    """Fields for an LLM_CALL event."""

    model: str = ""
    tier: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    operation: str = ""
    prompt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "tier": self.tier,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "operation": self.operation,
            "prompt_hash": self.prompt_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LLMCallFields:
        return cls(
            model=d.get("model", ""),
            tier=d.get("tier", ""),
            input_tokens=d.get("input_tokens", 0),
            output_tokens=d.get("output_tokens", 0),
            cost_usd=d.get("cost_usd", 0.0),
            latency_ms=d.get("latency_ms", 0.0),
            operation=d.get("operation", ""),
            prompt_hash=d.get("prompt_hash", ""),
        )


@dataclass
class AutonomousIterationFields:
    """Fields for an AUTONOMOUS_ITERATION event."""

    session_id: str = ""
    iteration: int = 0
    step_success: bool = False
    tokens_used: int = 0
    cost_usd: float = 0.0
    files_modified: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "iteration": self.iteration,
            "step_success": self.step_success,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "files_modified": self.files_modified,
            "violations": self.violations,
            "done": self.done,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AutonomousIterationFields:
        return cls(
            session_id=d.get("session_id", ""),
            iteration=d.get("iteration", 0),
            step_success=d.get("step_success", False),
            tokens_used=d.get("tokens_used", 0),
            cost_usd=d.get("cost_usd", 0.0),
            files_modified=d.get("files_modified", []),
            violations=d.get("violations", []),
            done=d.get("done", False),
        )


@dataclass
class ErrorFields:
    """Fields for an ERROR event."""

    error_type: str = ""
    message: str = ""
    module: str = ""
    traceback_str: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "module": self.module,
            "traceback": self.traceback_str,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ErrorFields:
        return cls(
            error_type=d.get("error_type", ""),
            message=d.get("message", ""),
            module=d.get("module", ""),
            traceback_str=d.get("traceback", ""),
        )


# =============================================================================
# Report Dataclasses
# =============================================================================


@dataclass
class CostReport:
    """Cost analysis report from LLM_CALL events."""

    total_cost_usd: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    by_operation: dict[str, float] = field(default_factory=dict)
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    period: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "by_model": self.by_model,
            "by_operation": self.by_operation,
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "period": self.period,
        }


@dataclass
class PerformanceReport:
    """Performance analysis from VERIFICATION and PROPOSAL events."""

    verification_latency_p50: float = 0.0
    verification_latency_p95: float = 0.0
    verification_latency_p99: float = 0.0
    approval_rate: float = 0.0
    total_proposals: int = 0
    total_verified: int = 0
    total_rejected: int = 0
    avg_claims_per_proposal: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_latency_p50": self.verification_latency_p50,
            "verification_latency_p95": self.verification_latency_p95,
            "verification_latency_p99": self.verification_latency_p99,
            "approval_rate": self.approval_rate,
            "total_proposals": self.total_proposals,
            "total_verified": self.total_verified,
            "total_rejected": self.total_rejected,
            "avg_claims_per_proposal": self.avg_claims_per_proposal,
        }


@dataclass
class LogStats:
    """Statistics about log files."""

    total_events: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_level: dict[str, int] = field(default_factory=dict)
    oldest: str = ""
    newest: str = ""
    log_files: list[str] = field(default_factory=list)
    total_size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "by_type": self.by_type,
            "by_level": self.by_level,
            "oldest": self.oldest,
            "newest": self.newest,
            "log_files": self.log_files,
            "total_size_bytes": self.total_size_bytes,
        }


# =============================================================================
# StructuredLogger (append-only JSONL)
# =============================================================================


class StructuredLogger:
    """Append-only JSON-line logger with date-partitioned files."""

    def __init__(self, log_dir: Path, config: TelemetryConfig | None = None):
        self.log_dir = log_dir
        self.config = config or TelemetryConfig()
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _current_log_path(self) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.log_dir / f"governor-{date_str}.jsonl"

    def _passes_level(self, level: TelemetryLevel) -> bool:
        min_order = LEVEL_ORDER.get(self.config.min_level_enum, 1)
        event_order = LEVEL_ORDER.get(level, 1)
        return event_order >= min_order

    def write(self, event: TelemetryEvent) -> None:
        """Append an event as a JSON line."""
        if not self._passes_level(event.level):
            return

        path = self._current_log_path()

        # Size rotation: if current file exceeds max, rotate
        max_bytes = int(self.config.log_max_size_mb * 1024 * 1024)
        if path.exists() and path.stat().st_size >= max_bytes:
            self._rotate_current(path)

        with open(path, "a") as f:
            f.write(event.to_json_line() + "\n")

    def _rotate_current(self, path: Path) -> None:
        """Rename current log file with numeric suffix."""
        suffix = 1
        while True:
            rotated = path.parent / f"{path.stem}.{suffix}{path.suffix}"
            if not rotated.exists():
                break
            suffix += 1
        path.rename(rotated)

    def read_events(
        self,
        last_n: int | None = None,
        event_type: TelemetryEventType | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[TelemetryEvent]:
        """Read events from log files with optional filters."""
        events: list[TelemetryEvent] = []

        for log_file in self.list_log_files():
            try:
                with open(log_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            ev = TelemetryEvent.from_dict(d)
                        except (json.JSONDecodeError, KeyError):
                            continue

                        # Filter by type
                        if event_type and ev.event_type != event_type:
                            continue

                        # Filter by since
                        if since and ev.timestamp < since:
                            continue

                        # Filter by until
                        if until and ev.timestamp > until:
                            continue

                        events.append(ev)
            except OSError:
                continue

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)

        # Apply last_n
        if last_n is not None and last_n > 0:
            events = events[-last_n:]

        return events

    def rotate_logs(self) -> int:
        """Delete log files older than retention_days. Returns count deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.log_retention_days)
        cutoff_str = cutoff.strftime("%Y%m%d")
        deleted = 0

        for log_file in self.list_log_files():
            # Extract date from filename: governor-YYYYMMDD.jsonl or governor-YYYYMMDD.N.jsonl
            name = log_file.stem  # governor-YYYYMMDD or governor-YYYYMMDD.N
            parts = name.split("-", 1)
            if len(parts) < 2:
                continue
            date_part = parts[1].split(".")[0]  # YYYYMMDD
            if len(date_part) == 8 and date_part.isdigit() and date_part < cutoff_str:
                try:
                    log_file.unlink()
                    deleted += 1
                except OSError:
                    pass

        return deleted

    def list_log_files(self) -> list[Path]:
        """List all log files sorted by name."""
        if not self.log_dir.exists():
            return []
        files = sorted(self.log_dir.glob("governor-*.jsonl"))
        return files

    def stats(self) -> LogStats:
        """Compute statistics across all log files."""
        result = LogStats()
        files = self.list_log_files()
        result.log_files = [str(f.name) for f in files]
        result.total_size_bytes = sum(f.stat().st_size for f in files if f.exists())

        oldest_ts = ""
        newest_ts = ""

        for log_file in files:
            try:
                with open(log_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        result.total_events += 1

                        et = d.get("event_type", "unknown")
                        result.by_type[et] = result.by_type.get(et, 0) + 1

                        lv = d.get("level", "unknown")
                        result.by_level[lv] = result.by_level.get(lv, 0) + 1

                        ts = d.get("timestamp", "")
                        if ts:
                            if not oldest_ts or ts < oldest_ts:
                                oldest_ts = ts
                            if not newest_ts or ts > newest_ts:
                                newest_ts = ts
            except OSError:
                continue

        result.oldest = oldest_ts
        result.newest = newest_ts
        return result


# =============================================================================
# Pluggable Backend
# =============================================================================


class TelemetryBackend(ABC):
    """Abstract base for telemetry backends."""

    @abstractmethod
    def record(self, event: TelemetryEvent) -> None:
        """Record a telemetry event."""


class LoggingBackend(TelemetryBackend):
    """Backend that writes to StructuredLogger."""

    def __init__(self, logger: StructuredLogger):
        self.logger = logger

    def record(self, event: TelemetryEvent) -> None:
        self.logger.write(event)


# =============================================================================
# TelemetryCollector
# =============================================================================


class TelemetryCollector:
    """
    Central event collector with pluggable backends.

    When logging_enabled=False, collector has no backends — all record_* calls
    become no-ops. Backend exceptions are silently swallowed to ensure
    telemetry never crashes the governor.
    """

    def __init__(
        self,
        config: TelemetryConfig | None = None,
        gov_dir: Path | None = None,
    ):
        self.config = config or TelemetryConfig()
        self.backends: list[TelemetryBackend] = []
        self._event_count = 0

        if self.config.logging_enabled and gov_dir is not None:
            log_dir = gov_dir / self.config.log_dir
            logger = StructuredLogger(log_dir, self.config)
            self.backends.append(LoggingBackend(logger))

    def add_backend(self, backend: TelemetryBackend) -> None:
        """Add a backend to receive events."""
        self.backends.append(backend)

    @property
    def event_count(self) -> int:
        return self._event_count

    def _emit(self, event: TelemetryEvent) -> None:
        """Send event to all backends, swallowing exceptions."""
        self._event_count += 1
        for backend in self.backends:
            try:
                backend.record(event)
            except Exception:
                pass  # Telemetry never crashes governor

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _redact_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Apply redaction rules to event fields."""
        result = dict(fields)
        if self.config.redact_file_contents and "file_contents" in result:
            result["file_contents"] = "[REDACTED]"
        if self.config.redact_prompts and "prompt" in result:
            result["prompt"] = "[REDACTED]"
        if self.config.redact_prompts and "prompt_hash" in result:
            # Keep hash, it's already opaque
            pass
        return result

    def record_proposal(
        self,
        proposal_id: str,
        claim_count: int = 0,
        claim_types: list[str] | None = None,
        envelope_mode: str = "strict",
        outcome: str = "proposed",
        agent_id: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Record a proposal event."""
        pf = ProposalFields(
            proposal_id=proposal_id,
            claim_count=claim_count,
            claim_types=claim_types or [],
            envelope_mode=envelope_mode,
            outcome=outcome,
        )
        event = TelemetryEvent(
            timestamp=self._now_iso(),
            event_type=TelemetryEventType.PROPOSAL,
            level=TelemetryLevel.INFO,
            fields=self._redact_fields(pf.to_dict()),
            agent_id=agent_id,
            duration_ms=duration_ms,
        )
        self._emit(event)

    def record_verification(
        self,
        proposal_id: str,
        claim_index: int = 0,
        claim_type: str = "",
        success: bool = False,
        error: str = "",
        receipt_type: str = "",
        agent_id: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Record a verification event."""
        vf = VerificationFields(
            proposal_id=proposal_id,
            claim_index=claim_index,
            claim_type=claim_type,
            success=success,
            error=error,
            receipt_type=receipt_type,
        )
        event = TelemetryEvent(
            timestamp=self._now_iso(),
            event_type=TelemetryEventType.VERIFICATION,
            level=TelemetryLevel.INFO if success else TelemetryLevel.WARN,
            fields=self._redact_fields(vf.to_dict()),
            agent_id=agent_id,
            duration_ms=duration_ms,
        )
        self._emit(event)

    def record_llm_call(
        self,
        model: str = "",
        tier: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        operation: str = "",
        prompt_hash: str = "",
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Record an LLM call event."""
        lf = LLMCallFields(
            model=model,
            tier=tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            operation=operation,
            prompt_hash=prompt_hash,
        )
        event = TelemetryEvent(
            timestamp=self._now_iso(),
            event_type=TelemetryEventType.LLM_CALL,
            level=TelemetryLevel.INFO,
            fields=self._redact_fields(lf.to_dict()),
            agent_id=agent_id,
            session_id=session_id,
            duration_ms=latency_ms,
        )
        self._emit(event)

    def record_autonomous_iteration(
        self,
        session_id: str = "",
        iteration: int = 0,
        step_success: bool = False,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        files_modified: list[str] | None = None,
        violations: list[str] | None = None,
        done: bool = False,
        agent_id: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Record an autonomous iteration event."""
        af = AutonomousIterationFields(
            session_id=session_id,
            iteration=iteration,
            step_success=step_success,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            files_modified=files_modified or [],
            violations=violations or [],
            done=done,
        )
        event = TelemetryEvent(
            timestamp=self._now_iso(),
            event_type=TelemetryEventType.AUTONOMOUS_ITERATION,
            level=TelemetryLevel.INFO,
            fields=self._redact_fields(af.to_dict()),
            agent_id=agent_id,
            session_id=session_id,
            duration_ms=duration_ms,
        )
        self._emit(event)

    def record_error(
        self,
        error_type: str = "",
        message: str = "",
        module: str = "",
        exc: Exception | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Record an error event."""
        tb_str = ""
        if exc is not None:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        ef = ErrorFields(
            error_type=error_type or (type(exc).__name__ if exc else ""),
            message=message or (str(exc) if exc else ""),
            module=module,
            traceback_str=tb_str,
        )
        event = TelemetryEvent(
            timestamp=self._now_iso(),
            event_type=TelemetryEventType.ERROR,
            level=TelemetryLevel.ERROR,
            fields=self._redact_fields(ef.to_dict()),
            agent_id=agent_id,
        )
        self._emit(event)


# =============================================================================
# Analysis Functions
# =============================================================================


def _percentile(values: list[float], p: float) -> float:
    """Compute percentile from sorted list. No numpy dependency."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    index = math.ceil(p * n) - 1
    index = max(0, min(index, n - 1))
    return sorted_vals[index]


def analyze_costs(
    events: list[TelemetryEvent],
    since: str | None = None,
) -> CostReport:
    """Analyze costs from LLM_CALL events."""
    report = CostReport()

    filtered = [
        e for e in events
        if e.event_type == TelemetryEventType.LLM_CALL
        and (since is None or e.timestamp >= since)
    ]

    for ev in filtered:
        f = ev.fields
        cost = f.get("cost_usd", 0.0)
        model = f.get("model", "unknown")
        operation = f.get("operation", "unknown")
        inp = f.get("input_tokens", 0)
        out = f.get("output_tokens", 0)

        report.total_cost_usd += cost
        report.total_calls += 1
        report.total_input_tokens += inp
        report.total_output_tokens += out
        report.by_model[model] = report.by_model.get(model, 0.0) + cost
        report.by_operation[operation] = report.by_operation.get(operation, 0.0) + cost

    if since:
        report.period = f"since {since}"
    elif filtered:
        report.period = f"{filtered[0].timestamp} to {filtered[-1].timestamp}"

    return report


def analyze_performance(events: list[TelemetryEvent]) -> PerformanceReport:
    """Analyze performance from VERIFICATION and PROPOSAL events."""
    report = PerformanceReport()

    # Gather verification latencies
    latencies: list[float] = []
    for ev in events:
        if ev.event_type == TelemetryEventType.VERIFICATION and ev.duration_ms is not None:
            latencies.append(ev.duration_ms)

    if latencies:
        report.verification_latency_p50 = _percentile(latencies, 0.50)
        report.verification_latency_p95 = _percentile(latencies, 0.95)
        report.verification_latency_p99 = _percentile(latencies, 0.99)

    # Gather proposal stats
    claim_counts: list[int] = []
    for ev in events:
        if ev.event_type == TelemetryEventType.PROPOSAL:
            report.total_proposals += 1
            outcome = ev.fields.get("outcome", "")
            if outcome in ("verified", "applied"):
                report.total_verified += 1
            elif outcome == "rejected":
                report.total_rejected += 1
            cc = ev.fields.get("claim_count", 0)
            if cc:
                claim_counts.append(cc)

    if report.total_proposals > 0:
        report.approval_rate = report.total_verified / report.total_proposals

    if claim_counts:
        report.avg_claims_per_proposal = sum(claim_counts) / len(claim_counts)

    return report


# =============================================================================
# Export
# =============================================================================


def export_events(
    events: list[TelemetryEvent],
    output_path: Path,
    fmt: str = "json",
) -> int:
    """Export events to a file. Returns count exported."""
    if not events:
        # Write empty output
        if fmt == "csv":
            output_path.write_text("")
        else:
            output_path.write_text("[]\n")
        return 0

    if fmt == "csv":
        return _export_csv(events, output_path)
    else:
        return _export_json(events, output_path)


def _export_json(events: list[TelemetryEvent], output_path: Path) -> int:
    data = [e.to_dict() for e in events]
    output_path.write_text(json.dumps(data, indent=2) + "\n")
    return len(data)


def _export_csv(events: list[TelemetryEvent], output_path: Path) -> int:
    """Export events as CSV, flattening fields with 'fields.' prefix."""
    if not events:
        output_path.write_text("")
        return 0

    # Collect all field keys across events
    all_field_keys: set[str] = set()
    rows: list[dict[str, Any]] = []
    for ev in events:
        row: dict[str, Any] = {
            "timestamp": ev.timestamp,
            "event_type": ev.event_type.value if isinstance(ev.event_type, Enum) else ev.event_type,
            "level": ev.level.value if isinstance(ev.level, Enum) else ev.level,
            "event_id": ev.event_id,
            "agent_id": ev.agent_id or "",
            "session_id": ev.session_id or "",
            "duration_ms": ev.duration_ms if ev.duration_ms is not None else "",
        }
        for k, v in ev.fields.items():
            key = f"fields.{k}"
            all_field_keys.add(key)
            if isinstance(v, (list, dict)):
                row[key] = json.dumps(v)
            else:
                row[key] = v
        rows.append(row)

    base_cols = ["timestamp", "event_type", "level", "event_id", "agent_id", "session_id", "duration_ms"]
    field_cols = sorted(all_field_keys)
    all_cols = base_cols + field_cols

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=all_cols, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    output_path.write_text(buf.getvalue())
    return len(rows)


# =============================================================================
# Convenience
# =============================================================================


def get_collector(gov_dir: Path | None = None) -> TelemetryCollector:
    """Create a TelemetryCollector from a governor directory."""
    if gov_dir is None:
        return TelemetryCollector(config=TelemetryConfig(logging_enabled=False))
    config = TelemetryConfig.load(gov_dir)
    return TelemetryCollector(config=config, gov_dir=gov_dir)


def get_logger(gov_dir: Path) -> StructuredLogger:
    """Create a StructuredLogger from a governor directory."""
    config = TelemetryConfig.load(gov_dir)
    log_dir = gov_dir / config.log_dir
    return StructuredLogger(log_dir, config)


def hash_prompt(text: str) -> str:
    """Hash a prompt for telemetry (privacy-preserving)."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]
