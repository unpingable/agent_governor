# SPDX-License-Identifier: Apache-2.0
"""
Signal Store — SQLite projection cache over the instrumentation spine JSONL.

The JSONL append log (signals/emit.py::JsonlSink) remains source of truth.
SQLite is a disposable index: drop + rebuild from JSONL at any time.

Design invariants:
  - Cursor on byte offset, not line count.  Inode change or file shrink →
    reset cursor to 0, re-ingest with INSERT OR IGNORE (no data loss).
  - signal_hash = envelope.content_hash() — content-addressed identity.
  - envelope_json = envelope.to_canonical_bytes() — exact hash preimage.
  - Queries return projected columns only; envelope deserialization is
    opt-in (get/explain).
  - Write exclusivity via fcntl.flock; reads are lock-free (SQLite WAL).
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .signals.envelope import SignalEnvelope

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS signals (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_hash TEXT NOT NULL UNIQUE,
    emitted_at TEXT NOT NULL,
    signal_name TEXT NOT NULL,
    phase TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    value REAL,
    subject_type TEXT NOT NULL,
    subject_id TEXT,
    session_id TEXT,
    correlation_id TEXT,
    activity_id TEXT,
    window_start TEXT,
    window_end TEXT,
    source_offset INTEGER,
    envelope_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_emitted_at ON signals(emitted_at);
CREATE INDEX IF NOT EXISTS idx_signals_name ON signals(signal_name, emitted_at);
CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session_id, emitted_at);
CREATE INDEX IF NOT EXISTS idx_signals_phase ON signals(phase, emitted_at);

CREATE TABLE IF NOT EXISTS ingest_cursor (
    source TEXT PRIMARY KEY,
    byte_offset INTEGER NOT NULL,
    file_inode INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Projected columns returned by list/tail/query (no envelope blob).
_PROJECTED_COLS = (
    "seq", "signal_hash", "emitted_at", "signal_name", "phase",
    "schema_version", "quality_status", "value", "subject_type",
    "subject_id", "session_id", "correlation_id", "activity_id",
    "window_start", "window_end", "source_offset",
)


# ---------------------------------------------------------------------------
# Pure projection function
# ---------------------------------------------------------------------------


def project_envelope(
    envelope: SignalEnvelope,
    *,
    source_offset: int | None = None,
) -> dict[str, Any]:
    """Extract query columns from a SignalEnvelope.

    Maps envelope.signal_id → signal_name column.
    Computes signal_hash via envelope.content_hash().
    Serializes envelope_json via envelope.to_canonical_bytes().
    """
    return {
        "signal_hash": envelope.content_hash(),
        "emitted_at": envelope.emitted_at,
        "signal_name": envelope.signal_id,
        "phase": envelope.phase,
        "schema_version": envelope.schema_version,
        "quality_status": envelope.quality_status,
        "value": envelope.value,
        "subject_type": envelope.subject_type,
        "subject_id": envelope.subject_id,
        "session_id": envelope.session_id,
        "correlation_id": envelope.correlation_id,
        "activity_id": getattr(envelope, "activity_id", None),
        "window_start": envelope.window_start,
        "window_end": envelope.window_end,
        "source_offset": source_offset,
        "envelope_json": envelope.to_canonical_bytes().decode("utf-8"),
    }


# ---------------------------------------------------------------------------
# Ingest result
# ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    """Result of an incremental ingest operation."""
    inserted: int = 0
    malformed: int = 0
    duplicates: int = 0
    cursor_reset: bool = False


# ---------------------------------------------------------------------------
# Signal Store
# ---------------------------------------------------------------------------

# Query limit bounds.
_MAX_QUERY_LIMIT = 1000
_DEFAULT_QUERY_LIMIT = 50
_DEFAULT_TAIL_LIMIT = 20


class SignalStore:
    """SQLite projection cache over the signal JSONL append log."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            isolation_level=None,  # autocommit; we manage transactions
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create tables + indexes if missing (idempotent)."""
        self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Single insert
    # ------------------------------------------------------------------

    def insert(
        self,
        envelope: SignalEnvelope,
        *,
        source_offset: int | None = None,
    ) -> bool:
        """Project and INSERT OR IGNORE a single envelope.

        Returns True if a new row was inserted (not duplicate).
        """
        row = project_envelope(envelope, source_offset=source_offset)
        cur = self._conn.execute(
            """INSERT OR IGNORE INTO signals (
                signal_hash, emitted_at, signal_name, phase,
                schema_version, quality_status, value,
                subject_type, subject_id, session_id,
                correlation_id, activity_id,
                window_start, window_end, source_offset,
                envelope_json
            ) VALUES (
                :signal_hash, :emitted_at, :signal_name, :phase,
                :schema_version, :quality_status, :value,
                :subject_type, :subject_id, :session_id,
                :correlation_id, :activity_id,
                :window_start, :window_end, :source_offset,
                :envelope_json
            )""",
            row,
        )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # JSONL incremental ingest
    # ------------------------------------------------------------------

    def _acquire_lock(self):
        """Acquire exclusive file lock for write operations."""
        lock_path = str(self._db_path) + ".lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _release_lock(self, fd: int) -> None:
        """Release file lock."""
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def ingest_from_jsonl(self, jsonl_path: Path) -> IngestResult:
        """Incremental byte-offset cursor ingest from JSONL file.

        - Inode change or file shrink → reset cursor to 0 (INSERT OR IGNORE
          handles dedup; existing rows preserved).
        - Partial last line → don't advance cursor past last good newline.
        - All inserts inside BEGIN IMMEDIATE (one fsync, atomic commit).
        - Cursor updated AFTER successful commit.
        """
        jsonl_path = Path(jsonl_path)
        result = IngestResult()

        if not jsonl_path.exists():
            return result

        stat = jsonl_path.stat()
        file_size = stat.st_size
        file_inode = stat.st_ino

        if file_size == 0:
            return result

        # Load cursor
        source_key = str(jsonl_path)
        cursor_row = self._conn.execute(
            "SELECT byte_offset, file_inode FROM ingest_cursor WHERE source = ?",
            (source_key,),
        ).fetchone()

        cursor_offset = 0
        if cursor_row is not None:
            stored_offset = cursor_row["byte_offset"]
            stored_inode = cursor_row["file_inode"]

            if stored_inode != file_inode or file_size < stored_offset:
                # Inode changed or file shrank → reset cursor, re-ingest
                result.cursor_reset = True
                cursor_offset = 0
                logger.warning(
                    "Signal JSONL cursor reset: inode_changed=%s file_shrank=%s "
                    "path=%s",
                    stored_inode != file_inode,
                    file_size < stored_offset,
                    jsonl_path,
                )
            else:
                cursor_offset = stored_offset

        # Fast path: no new data
        if file_size == cursor_offset:
            return result

        # Acquire lock for write exclusivity
        lock_fd = self._acquire_lock()
        try:
            return self._do_ingest(
                jsonl_path, source_key, cursor_offset, file_size, file_inode,
                result,
            )
        finally:
            self._release_lock(lock_fd)

    def _do_ingest(
        self,
        jsonl_path: Path,
        source_key: str,
        cursor_offset: int,
        file_size: int,
        file_inode: int,
        result: IngestResult,
    ) -> IngestResult:
        """Inner ingest logic (caller holds lock)."""
        with open(jsonl_path, "rb") as f:
            f.seek(cursor_offset)
            raw = f.read()

        # Split into lines.  Track byte positions for partial-line safety.
        # raw may end without \n if writer hasn't flushed yet.
        lines = raw.split(b"\n")

        # If the last element is empty (file ended with \n), drop it.
        # If non-empty, it's a partial line — exclude from processing.
        partial_tail = b""
        if lines and lines[-1] == b"":
            lines = lines[:-1]
        elif lines:
            partial_tail = lines[-1]
            lines = lines[:-1]

        if not lines:
            return result

        # Compute byte offset of the end of the last fully-parsed line.
        # Each line contributes len(line_bytes) + 1 (for the \n separator).
        good_bytes = sum(len(line) + 1 for line in lines)
        new_cursor = cursor_offset + good_bytes

        rows_to_insert: list[dict[str, Any]] = []
        byte_pos = 0  # position within `raw`
        for line in lines:
            stripped = line.strip()
            if stripped:
                try:
                    data = json.loads(stripped)
                    envelope = SignalEnvelope.from_dict(data)
                    row = project_envelope(
                        envelope, source_offset=cursor_offset + byte_pos,
                    )
                    rows_to_insert.append(row)
                except Exception:
                    result.malformed += 1
                    logger.debug(
                        "Malformed signal line at offset ~%d: %s",
                        cursor_offset + byte_pos,
                        stripped[:100],
                    )
            byte_pos += len(line) + 1  # +1 for the \n separator

        # Batch insert inside transaction
        from datetime import datetime, timezone

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows_to_insert:
                cur = self._conn.execute(
                    """INSERT OR IGNORE INTO signals (
                        signal_hash, emitted_at, signal_name, phase,
                        schema_version, quality_status, value,
                        subject_type, subject_id, session_id,
                        correlation_id, activity_id,
                        window_start, window_end, source_offset,
                        envelope_json
                    ) VALUES (
                        :signal_hash, :emitted_at, :signal_name, :phase,
                        :schema_version, :quality_status, :value,
                        :subject_type, :subject_id, :session_id,
                        :correlation_id, :activity_id,
                        :window_start, :window_end, :source_offset,
                        :envelope_json
                    )""",
                    row,
                )
                if cur.rowcount > 0:
                    result.inserted += 1
                else:
                    result.duplicates += 1

            # Update cursor AFTER inserts succeed (inside same transaction).
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """INSERT OR REPLACE INTO ingest_cursor
                   (source, byte_offset, file_inode, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (source_key, new_cursor, file_inode, now),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

        return result

    # ------------------------------------------------------------------
    # Rebuild
    # ------------------------------------------------------------------

    def rebuild(self, jsonl_path: Path) -> int:
        """Drop all data and re-ingest from JSONL. Returns total inserted."""
        lock_fd = self._acquire_lock()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute("DELETE FROM signals")
                self._conn.execute("DELETE FROM ingest_cursor")
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

            # Re-ingest from offset 0 — cursor table is clean, so
            # ingest_from_jsonl will start from the beginning.
            result = self._do_ingest(
                Path(jsonl_path),
                str(jsonl_path),
                0,
                jsonl_path.stat().st_size if jsonl_path.exists() else 0,
                jsonl_path.stat().st_ino if jsonl_path.exists() else 0,
                IngestResult(),
            )
            return result.inserted
        finally:
            self._release_lock(lock_fd)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        signal_name: str | None = None,
        phase: str | None = None,
        quality: str | None = None,
        session_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = _DEFAULT_QUERY_LIMIT,
        after_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query signals with filters. Returns ascending by seq.

        Returns projected columns only (no envelope_json).
        """
        limit = max(1, min(limit, _MAX_QUERY_LIMIT))

        conditions: list[str] = []
        params: list[Any] = []

        if signal_name is not None:
            conditions.append("signal_name = ?")
            params.append(signal_name)
        if phase is not None:
            conditions.append("phase = ?")
            params.append(phase)
        if quality is not None:
            conditions.append("quality_status = ?")
            params.append(quality)
        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)
        if since is not None:
            conditions.append("emitted_at >= ?")
            params.append(since)
        if until is not None:
            conditions.append("emitted_at <= ?")
            params.append(until)
        if after_seq is not None:
            conditions.append("seq > ?")
            params.append(after_seq)

        cols = ", ".join(_PROJECTED_COLS)
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        sql = f"SELECT {cols} FROM signals WHERE {where} ORDER BY seq ASC LIMIT ?"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Get (single, with envelope)
    # ------------------------------------------------------------------

    def get(self, signal_hash: str) -> dict[str, Any] | None:
        """Get a single signal by hash. Returns full row including parsed envelope."""
        cols = ", ".join(_PROJECTED_COLS) + ", envelope_json"
        row = self._conn.execute(
            f"SELECT {cols} FROM signals WHERE signal_hash = ?",
            (signal_hash,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        # Parse envelope for callers that need the full object
        try:
            d["envelope"] = json.loads(d["envelope_json"])
        except Exception:
            d["envelope"] = None
        return d

    # ------------------------------------------------------------------
    # Tail
    # ------------------------------------------------------------------

    def tail(
        self,
        limit: int = _DEFAULT_TAIL_LIMIT,
        after_seq: int | None = None,
        signal_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Tail signals.

        With after_seq: rows with seq > after_seq, ascending (polling).
        Without: newest N, descending (display).
        signal_name: optional filter (e.g. "VERIFY_SUMMARY").
        """
        limit = max(1, min(limit, _MAX_QUERY_LIMIT))
        cols = ", ".join(_PROJECTED_COLS)

        conditions: list[str] = []
        params: list[Any] = []

        if after_seq is not None:
            conditions.append("seq > ?")
            params.append(after_seq)
        if signal_name is not None:
            conditions.append("signal_name = ?")
            params.append(signal_name)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        if after_seq is not None:
            sql = f"SELECT {cols} FROM signals WHERE {where} ORDER BY seq ASC LIMIT ?"
        else:
            sql = f"SELECT {cols} FROM signals WHERE {where} ORDER BY seq DESC LIMIT ?"

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self, jsonl_path: Path | None = None) -> dict[str, Any]:
        """Aggregate statistics about the signal store."""
        total = self.count()

        # By signal_name
        by_name: dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT signal_name, COUNT(*) as cnt FROM signals GROUP BY signal_name"
        ).fetchall():
            by_name[row["signal_name"]] = row["cnt"]

        # By phase
        by_phase: dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT phase, COUNT(*) as cnt FROM signals GROUP BY phase"
        ).fetchall():
            by_phase[row["phase"]] = row["cnt"]

        # By quality
        by_quality: dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT quality_status, COUNT(*) as cnt FROM signals GROUP BY quality_status"
        ).fetchall():
            by_quality[row["quality_status"]] = row["cnt"]

        # Time range
        time_row = self._conn.execute(
            "SELECT MIN(emitted_at) as earliest, MAX(emitted_at) as latest FROM signals"
        ).fetchone()
        time_range = {
            "earliest": time_row["earliest"] if time_row else None,
            "latest": time_row["latest"] if time_row else None,
        }

        # Ingest health
        ingest_health: dict[str, Any] = {
            "cursor_offset": 0,
            "file_size": 0,
            "lag_bytes": 0,
            "malformed_lines": 0,
            "duplicates_skipped": 0,
            "cursor_reset_detected": False,
        }
        if jsonl_path is not None:
            source_key = str(jsonl_path)
            cursor_row = self._conn.execute(
                "SELECT byte_offset, file_inode FROM ingest_cursor WHERE source = ?",
                (source_key,),
            ).fetchone()
            if cursor_row is not None:
                ingest_health["cursor_offset"] = cursor_row["byte_offset"]
            if jsonl_path.exists():
                st = jsonl_path.stat()
                ingest_health["file_size"] = st.st_size
                ingest_health["lag_bytes"] = max(
                    0, st.st_size - ingest_health["cursor_offset"]
                )
                # Check for inode mismatch or shrink — either means
                # the JSONL was rotated/truncated since last ingest.
                if cursor_row is not None:
                    inode_mismatch = cursor_row["file_inode"] != st.st_ino
                    file_shrank = st.st_size < cursor_row["byte_offset"]
                    if inode_mismatch or file_shrank:
                        ingest_health["cursor_reset_detected"] = True

        return {
            "total": total,
            "by_signal_name": by_name,
            "by_phase": by_phase,
            "by_quality": by_quality,
            "time_range": time_range,
            "ingest_health": ingest_health,
        }

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Total number of indexed signals."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM signals").fetchone()
        return row["cnt"] if row else 0


# ---------------------------------------------------------------------------
# Standalone JSONL envelope loader (no SQLite, no SignalStore)
# ---------------------------------------------------------------------------


def load_latest_envelopes(
    jsonl_path: Path,
    signal_names: list[str] | tuple[str, ...],
) -> dict[str, SignalEnvelope]:
    """Load the latest envelope for each requested signal name from JSONL.

    "Latest" = last occurrence in append order (file is append-only).
    Forward-scans the entire file, keeping the last-seen per name.  O(file)
    but the JSONL is small (hundreds of lines, not millions).

    Robustness:
      - Skips lines that fail json.loads (partial last line from concurrent write).
      - Skips envelopes whose schema_version doesn't match CURRENT_SCHEMA_VERSION.
    """
    from .signals.envelope import CURRENT_SCHEMA_VERSION

    if not jsonl_path.exists():
        return {}

    wanted = set(signal_names)
    latest: dict[str, SignalEnvelope] = {}

    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    logger.debug("load_latest_envelopes: skipping malformed line")
                    continue
                sv = data.get("schema_version")
                if sv != CURRENT_SCHEMA_VERSION:
                    continue
                sid = data.get("signal_id", "")
                if sid not in wanted:
                    continue
                try:
                    env = SignalEnvelope.from_dict(data)
                    latest[sid] = env
                except Exception:
                    logger.debug("load_latest_envelopes: failed to parse envelope for %s", sid)
    except OSError:
        logger.warning("load_latest_envelopes: cannot read %s", jsonl_path)

    return latest
