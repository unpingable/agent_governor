# SPDX-License-Identifier: Apache-2.0
"""
Signal emitter — interface + JSONL sink for SignalEnvelope.

Keeps derivation code separate from emission transport so derivations
can be replayed later (Phase C) without dragging runtime IO.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .envelope import CURRENT_SCHEMA_VERSION, SignalEnvelope, validate_envelope

logger = logging.getLogger(__name__)

SIGNAL_EMIT_FAILED = "SIGNAL_EMIT_FAILED"
SIGNAL_EMIT_FAILED_VERSION = 1


def build_emit_failed_envelope(
    failed_signal_id: str,
    error_type: str,
    error_message: str,
    *,
    emitter: str = "governor.signals.emit",
    emitter_version: str = "1",
    session_id: str | None = None,
) -> SignalEnvelope:
    """Build a SIGNAL_EMIT_FAILED envelope for a failed emission.

    Pure function. The envelope records what failed and why, so the failure
    is queryable in the same signal plane. quality_status is always "partial"
    because we know something happened but the original signal was lost.
    """
    values: dict[str, Any] = {
        "failed_signal_id": failed_signal_id,
        "error_type": error_type,
        "error_message": error_message[:500],  # cap message length
    }

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id=SIGNAL_EMIT_FAILED,
        signal_version=SIGNAL_EMIT_FAILED_VERSION,
        phase="2.5",
        derivation="direct",
        derivation_version="1",
        subject_type="signal",
        subject_id=failed_signal_id,
        session_id=session_id or "",
        value=None,
        quality_status="partial",
        values=values,
    )


@runtime_checkable
class SignalEmitter(Protocol):
    """Protocol for signal emission sinks."""

    def emit(self, envelope: SignalEnvelope) -> None:
        """Emit a signal envelope. Must not raise on transient failures."""
        ...


class JsonlSink:
    """Append-only JSONL file sink for signal envelopes.

    Validates envelopes before writing. Invalid envelopes are logged and
    skipped (observe-only — never blocks on emission failure).

    Uses O_APPEND + fcntl.flock for concurrent-safe writes (same pattern
    as semantic_stability.py JSONL persistence).
    """

    def __init__(self, path: Path, *, validate: bool = True) -> None:
        self._path = path
        self._validate = validate

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, envelope: SignalEnvelope) -> None:
        """Append envelope as one JSON line. Never raises."""
        try:
            if self._validate:
                errors = validate_envelope(envelope)
                if errors:
                    logger.warning(
                        "Signal envelope validation failed for %s: %s",
                        envelope.signal_id,
                        "; ".join(errors),
                    )
                    return

            line = json.dumps(
                envelope.to_dict(), separators=(",", ":"), ensure_ascii=True,
            )

            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                str(self._path),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, (line + "\n").encode("utf-8"))
            finally:
                os.close(fd)

        except Exception as exc:
            # Observe-only: emission failure must never block execution
            signal_id = getattr(envelope, "signal_id", "unknown")
            logger.exception(
                "Failed to emit signal envelope for %s", signal_id,
            )
            # Best-effort: record the failure in the same JSONL
            self._try_write_emit_failed(signal_id, exc)

    def _try_write_emit_failed(self, failed_signal_id: str, exc: Exception) -> None:
        """Best-effort write of SIGNAL_EMIT_FAILED. No recursion, no raise."""
        try:
            fail_env = build_emit_failed_envelope(
                failed_signal_id=failed_signal_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            line = json.dumps(
                fail_env.to_dict(), separators=(",", ":"), ensure_ascii=True,
            )
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                str(self._path),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, (line + "\n").encode("utf-8"))
            finally:
                os.close(fd)
        except Exception:
            # If even the failure signal can't be written, just log
            logger.debug("Could not emit SIGNAL_EMIT_FAILED (sink broken)", exc_info=True)

    def read_all(self) -> list[SignalEnvelope]:
        """Read all envelopes from the JSONL file. For testing/replay."""
        if not self._path.exists():
            return []
        envelopes = []
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                envelopes.append(SignalEnvelope.from_json(line))
            except Exception:
                logger.warning("Skipping malformed signal line: %s", line[:100])
        return envelopes

    def count(self) -> int:
        """Count envelopes in the file without fully parsing."""
        if not self._path.exists():
            return 0
        return sum(
            1 for line in self._path.read_text().splitlines()
            if line.strip()
        )


class MultiSink:
    """Fan-out emitter: writes to multiple sinks."""

    def __init__(self, sinks: list[SignalEmitter]) -> None:
        self._sinks = list(sinks)

    def emit(self, envelope: SignalEnvelope) -> None:
        for sink in self._sinks:
            try:
                sink.emit(envelope)
            except Exception:
                logger.exception("Sink %s failed", type(sink).__name__)
