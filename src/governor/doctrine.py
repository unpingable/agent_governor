# SPDX-License-Identifier: Apache-2.0
"""
Doctrine consultation: read-only edge from Governor → Continuity.

This is a one-move-ahead slice. It does NOT enforce, block, or even propose
new behavior. It consults declared doctrine memories from a Continuity store
and emits an observational gate receipt naming what was considered.

Architectural shape:
    Continuity stores doctrine as committed memories (kind=constraint, etc.)
    Governor consults at the action boundary
    Receipts name which doctrine influenced the route

What this module does NOT do:
    - Add a new memory kind to Continuity (uses existing CONSTRAINT)
    - Add a new gate type or change the FSM
    - Block, warn, or otherwise enforce
    - Make Governor depend on Continuity (graceful degradation if absent)
    - Resolve doctrine conflicts (none yet — first one is the only one)
    - Cache, batch, or pre-fetch (boring synchronous reads)

It is the smallest possible Governor↔Continuity integration that proves
the shape: read latest committed memory in scope, capture rely_ok at
consultation time, name everything in a receipt.

If continuity is not installed in the active environment, every consult()
returns a degraded-but-shaped result with quality="unavailable" so callers
can still emit a meaningful receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# Optional continuity import
# =============================================================================

# We deliberately do not import continuity at module load. The whole point
# of "Governor as traffic cop, not city" is that it must work standalone.
# Each consult() call performs a fresh import attempt so an environment
# without continuity returns degraded-but-structured results instead of
# raising at module import time.

def _try_import_continuity() -> dict[str, Any] | None:
    """Return continuity API handles, or None if unavailable.

    Returns a dict so callers can dispatch on a single None check rather
    than catching ImportError around every API method.
    """
    try:
        from continuity import __version__ as continuity_version
        from continuity.api.models import MemoryKind, MemoryStatus
        from continuity.store.sqlite import SQLiteStore
        from continuity.util.dbpath import resolve_db_path, source_to_scope_kind
    except ImportError:
        return None

    return {
        "version": continuity_version,
        "MemoryKind": MemoryKind,
        "MemoryStatus": MemoryStatus,
        "SQLiteStore": SQLiteStore,
        "resolve_db_path": resolve_db_path,
        "source_to_scope_kind": source_to_scope_kind,
    }


# =============================================================================
# Result types
# =============================================================================


@dataclass(frozen=True)
class DoctrineEntry:
    """One memory consulted in a doctrine read.

    rely_ok and rely_reason are captured at consultation time, not stored.
    A doctrine memory whose hard premises got revoked is "found but not
    relyable" — that distinction must survive into the receipt.
    """

    memory_id: str
    scope: str
    kind: str
    status: str
    reliance_class: str
    confidence: float
    content: dict[str, Any]
    updated_at: str
    rely_ok: bool
    rely_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "scope": self.scope,
            "kind": self.kind,
            "status": self.status,
            "reliance_class": self.reliance_class,
            "confidence": self.confidence,
            "content": self.content,
            "updated_at": self.updated_at,
            "rely_ok": self.rely_ok,
            "rely_reason": self.rely_reason,
        }


@dataclass(frozen=True)
class ConsultationResult:
    """The structured result of a single doctrine consultation.

    quality:
        "ok"          — continuity available, store reachable, query ran
        "unavailable" — continuity not installed in this environment
        "store_error" — continuity present but the store could not be read

    entries: one DoctrineEntry per (scope, kind) pair that had a chain head.
    Empty list is valid — it means "no current doctrine for that scope/kind",
    which is itself a meaningful audit signal.
    """

    quality: str
    scope: str
    kinds: tuple[str, ...]
    entries: list[DoctrineEntry] = field(default_factory=list)
    db_path: str | None = None
    resolver_source: str | None = None
    scope_kind: str | None = None
    store_metadata: dict[str, Any] | None = None
    continuity_version: str | None = None
    error: str | None = None

    def to_evidence_bundle(self) -> dict[str, Any]:
        """Convert to a gate receipt evidence bundle (canonical-JSON-friendly)."""
        bundle: dict[str, Any] = {
            "quality": self.quality,
            "scope": self.scope,
            "kinds": list(self.kinds),
            "entry_count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }
        if self.db_path is not None:
            bundle["db_path"] = self.db_path
        if self.resolver_source is not None:
            bundle["resolver_source"] = self.resolver_source
        if self.scope_kind is not None:
            bundle["scope_kind"] = self.scope_kind
        if self.store_metadata is not None:
            bundle["store_metadata"] = self.store_metadata
        if self.continuity_version is not None:
            bundle["continuity_version"] = self.continuity_version
        if self.error is not None:
            bundle["error"] = self.error
        return bundle


# =============================================================================
# Consult
# =============================================================================


# Default kinds queried for doctrine. Both are existing continuity memory
# kinds — no schema additions. constraint covers declared rules; decision
# covers normative choices. We do not introduce a "doctrine" kind unless
# real semantics demand one.
DEFAULT_DOCTRINE_KINDS: tuple[str, ...] = ("constraint", "decision")


def consult(
    scope: str,
    *,
    kinds: tuple[str, ...] = DEFAULT_DOCTRINE_KINDS,
    explicit_db: Path | str | None = None,
    workspace: str | None = None,
    cwd: Path | None = None,
) -> ConsultationResult:
    """Consult declared doctrine for a given scope.

    For each requested kind, fetch the latest committed memory at that
    (scope, kind) pair via continuity's supersede-aware latest_memory.
    Capture rely_ok at the moment of consultation. Return a structured
    result that can be turned into a gate receipt evidence bundle.

    This function never raises on missing continuity, missing store, or
    empty results. All failure modes degrade into a result with a quality
    label other than "ok" so the caller can still emit a meaningful
    receipt and surface the degradation.

    Args:
        scope: continuity memory scope to query (e.g. "doctrine:debugging-discipline")
        kinds: which memory kinds to consider doctrine. Default: ("constraint", "decision")
        explicit_db: override resolver, point at a specific db file
        workspace: pass through to continuity's resolver as workspace selection
        cwd: pass through to continuity's resolver for git-root walk

    Returns:
        ConsultationResult with one DoctrineEntry per kind that had a chain head.
    """
    api = _try_import_continuity()
    if api is None:
        return ConsultationResult(
            quality="unavailable",
            scope=scope,
            kinds=tuple(kinds),
            error="continuity package not installed in this environment",
        )

    try:
        db_path, source = api["resolve_db_path"](
            explicit_db,
            workspace=workspace,
            cwd=cwd,
        )
        scope_kind = api["source_to_scope_kind"](source)
    except Exception as exc:  # pragma: no cover - resolver should not raise
        return ConsultationResult(
            quality="store_error",
            scope=scope,
            kinds=tuple(kinds),
            continuity_version=api["version"],
            error=f"resolver failed: {exc}",
        )

    if not Path(db_path).exists():
        return ConsultationResult(
            quality="store_error",
            scope=scope,
            kinds=tuple(kinds),
            db_path=str(db_path),
            resolver_source=source,
            scope_kind=scope_kind,
            continuity_version=api["version"],
            error=f"continuity db not found at {db_path}",
        )

    try:
        store = api["SQLiteStore"](db_path)
        store_metadata = store.get_store_metadata()

        entries: list[DoctrineEntry] = []
        for kind in kinds:
            mem = store.latest_memory(
                scope=scope,
                kind=kind,
                status=api["MemoryStatus"].COMMITTED,
            )
            if mem is None:
                continue
            explained = store.explain_memory(mem.memory_id)
            entries.append(
                DoctrineEntry(
                    memory_id=mem.memory_id,
                    scope=mem.scope,
                    kind=str(mem.kind),
                    status=str(mem.status),
                    reliance_class=str(mem.reliance_class),
                    confidence=float(mem.confidence),
                    content=dict(mem.content),
                    updated_at=str(mem.updated_at),
                    rely_ok=bool(explained.rely_ok),
                    rely_reason=str(explained.rely_reason),
                )
            )
    except Exception as exc:
        return ConsultationResult(
            quality="store_error",
            scope=scope,
            kinds=tuple(kinds),
            db_path=str(db_path),
            resolver_source=source,
            scope_kind=scope_kind,
            continuity_version=api["version"],
            error=f"store read failed: {exc.__class__.__name__}: {exc}",
        )

    return ConsultationResult(
        quality="ok",
        scope=scope,
        kinds=tuple(kinds),
        entries=entries,
        db_path=str(db_path),
        resolver_source=source,
        scope_kind=scope_kind,
        store_metadata=store_metadata,
        continuity_version=api["version"],
    )


# =============================================================================
# Receipt emission
# =============================================================================


GATE_NAME = "doctrine_consult"


def emit_consult_receipt(
    result: ConsultationResult,
    gov_dir: Path,
    *,
    principal_id: str = "local",
) -> Any:
    """Emit a gate receipt for a doctrine consultation and return it.

    Verdict is always "observe" — this slice is advisory. The receipt
    captures the full evidence bundle (which entries were consulted,
    with rely_ok), the resolver source, the store metadata, and the
    continuity version that produced the answer.
    """
    from .gate_receipt import GateReceiptSystem, VERDICT_OBSERVE

    system = GateReceiptSystem(gov_dir)

    # Subject is the query itself, canonicalized for content addressing.
    subject_repr = f"{result.scope}|{','.join(sorted(result.kinds))}".encode("utf-8")

    gate_config = {
        "kinds": list(result.kinds),
        "policy_version": "doctrine-consult-v0",
        "advisory_only": True,
    }

    return system.emit(
        gate=GATE_NAME,
        verdict=VERDICT_OBSERVE,
        subject_kind="doctrine_query",
        subject_bytes=subject_repr,
        evidence_bundle=result.to_evidence_bundle(),
        gate_config=gate_config,
        principal_id=principal_id,
    )
