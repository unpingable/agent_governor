# SPDX-License-Identifier: Apache-2.0
"""
Gate Receipt: content-addressed decision receipts for governor gates.

Every gate (evidence gate, pre-commit, wrapper, etc.) emits a GateReceipt
after checking a subject. Receipts are append-only, content-addressed,
and queryable.

Design choices (informed by ChatGPT review):
- receipt_id = H(schema_version + gate + subject_hash + evidence_hash + policy_hash + receipt_role)
  This is truly content-addressed: same policy + same subject + same evidence + same role
  = same receipt_id.  Timestamp is metadata, not identity.  receipt_role is included because
  role changes semantics — a measurement and a reset with the same payload are different.
- Evidence blobs are stored separately by evidence_hash (content-addressed).
  Receipt rows are tiny and queryable; evidence is deduplicated.
- Canonical JSON (sorted keys, no whitespace, stable floats) prevents hash
  churn from serialization non-determinism.
- subject_hash includes a subject_kind tag so "same bytes, different meaning"
  doesn't collide.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =============================================================================
# Schema
# =============================================================================

RECEIPT_SCHEMA_VERSION = 3


# =============================================================================
# Receipt Roles (3.x seam — what role does this receipt play?)
# =============================================================================

ROLE_MEASUREMENT = "measurement"
ROLE_PROPOSAL = "proposal"
ROLE_AUTHORITY = "authority"
ROLE_RECOVERY_PLAN = "recovery_plan"
ROLE_RESET = "reset"
VALID_RECEIPT_ROLES = frozenset({
    ROLE_MEASUREMENT, ROLE_PROPOSAL, ROLE_AUTHORITY,
    ROLE_RECOVERY_PLAN, ROLE_RESET,
})


# =============================================================================
# Verdict vocabulary (closed set — see GOVERNANCE_ABUSE_AUDIT.md §P3/A3)
# =============================================================================

VERDICT_PASS = "pass"
VERDICT_WARN = "warn"
VERDICT_BLOCK = "block"
VERDICT_OBSERVE = "observe"
VERDICT_PROCEED = "proceed"
VALID_VERDICTS = frozenset({
    VERDICT_PASS, VERDICT_WARN, VERDICT_BLOCK,
    VERDICT_OBSERVE, VERDICT_PROCEED,
})


# =============================================================================
# Canonicalization
# =============================================================================


def canonical_json(obj: dict[str, Any]) -> bytes:
    """Deterministic JSON: sorted keys, compact separators, ASCII-safe.

    This is the canonical form used for all hashing.  Do not change
    the parameters without bumping RECEIPT_SCHEMA_VERSION.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def content_hash(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def subject_hash(kind: str, content: bytes) -> str:
    """Hash subject with a kind tag to prevent cross-type collisions.

    kind: "text", "diff", "file_snapshot", etc.
    content: the raw bytes being checked.
    """
    return content_hash(kind.encode("utf-8") + b"\x00" + content)


def policy_hash(config_dict: dict[str, Any]) -> str:
    """Hash the gate's config/thresholds at check time."""
    return content_hash(canonical_json(config_dict))


def make_timing(
    start_ns: int,
    end_ns: int,
    *,
    budget_ms: float | None = None,
    budget_source: str | None = None,
) -> dict[str, Any]:
    """Create a timing fragment for a gate receipt.

    start_ns/end_ns: monotonic nanoseconds (time.monotonic_ns()).
    budget_ms/budget_source: which budget applied and where it came from.

    Timing is metadata — NOT part of receipt_id.  It exists so SLA
    measurement is possible before SLA enforcement.
    """
    t: dict[str, Any] = {
        "start_ns": start_ns,
        "end_ns": end_ns,
        "duration_ms": (end_ns - start_ns) / 1_000_000,
    }
    if budget_ms is not None:
        t["budget_ms"] = budget_ms
    if budget_source is not None:
        t["budget_source"] = budget_source
    return t


def _compute_receipt_id(
    schema_version: int,
    gate: str,
    s_hash: str,
    e_hash: str,
    p_hash: str,
    receipt_role: str = ROLE_MEASUREMENT,
) -> str:
    """Content-addressed receipt identity.

    Same policy + same subject + same evidence + same role = same receipt_id.
    Timestamp is deliberately excluded — it's metadata, not identity.
    receipt_role is included because role changes semantics — two receipts with
    the same payload but different roles are not the same thing.
    """
    payload = f"{schema_version}:{gate}:{s_hash}:{e_hash}:{p_hash}:{receipt_role}"
    return content_hash(payload.encode("utf-8"))


# =============================================================================
# GateReceipt
# =============================================================================


@dataclass(frozen=True)
class GateReceipt:
    """A content-addressed decision receipt from a governor gate.

    Fields:
        receipt_id       H(schema_version + gate + subject_hash + evidence_hash + policy_hash + receipt_role)
        schema_version   Protocol version (bump on breaking changes)
        timestamp        ISO 8601 UTC — ordering metadata, NOT identity
        gate             Which gate produced this receipt
        verdict          one of VALID_VERDICTS: "pass" | "warn" | "block" | "observe" | "proceed"
        subject_hash     H(subject_kind + \\x00 + subject_bytes)
        evidence_hash    H(canonical_json(evidence_bundle))
        policy_hash      H(canonical_json(gate_config))
        principal_id     Who initiated the action (default "local")
        tenant_id        Isolation boundary (default "default")
        auth_method      How the principal was authenticated (default "none")

    principal_id, tenant_id, and auth_method are metadata (like timestamp) —
    they do NOT affect receipt_id.  They exist so the audit log has the right
    shape before multi-tenant auth is implemented.

    receipt_role IS part of receipt_id — role changes semantics (a measurement
    receipt and a reset receipt with the same payload are not the same thing).
    """

    receipt_id: str
    schema_version: int
    timestamp: str
    gate: str
    verdict: str
    subject_hash: str
    evidence_hash: str
    policy_hash: str
    principal_id: str = "local"
    tenant_id: str = "default"
    auth_method: str = "none"
    receipt_role: str = ROLE_MEASUREMENT
    timing: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(
                f"Invalid verdict {self.verdict!r}; "
                f"must be one of {sorted(VALID_VERDICTS)}"
            )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "receipt_id": self.receipt_id,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "gate": self.gate,
            "verdict": self.verdict,
            "subject_hash": self.subject_hash,
            "evidence_hash": self.evidence_hash,
            "policy_hash": self.policy_hash,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "auth_method": self.auth_method,
            "receipt_role": self.receipt_role,
        }
        if self.timing is not None:
            d["timing"] = self.timing
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GateReceipt:
        v = data.get("schema_version", 1)  # Missing → legacy v1
        # Legacy receipts stored schema_version as string ("receipt_v1")
        if isinstance(v, str):
            v = 1
        if v > RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"Receipt schema version {v} is newer than supported "
                f"({RECEIPT_SCHEMA_VERSION}). Upgrade governor."
            )
        return cls(
            receipt_id=data["receipt_id"],
            schema_version=v,
            timestamp=data["timestamp"],
            gate=data["gate"],
            verdict=data["verdict"],
            subject_hash=data["subject_hash"],
            evidence_hash=data["evidence_hash"],
            policy_hash=data["policy_hash"],
            principal_id=data.get("principal_id", "local"),
            tenant_id=data.get("tenant_id", "default"),
            auth_method=data.get("auth_method", "none"),
            receipt_role=data.get("receipt_role", ROLE_MEASUREMENT),
            timing=data.get("timing"),
        )


def create_receipt(
    gate: str,
    verdict: str,
    subject_kind: str,
    subject_bytes: bytes,
    evidence_bundle: dict[str, Any],
    gate_config: dict[str, Any],
    timestamp: str | None = None,
    principal_id: str = "local",
    tenant_id: str = "default",
    auth_method: str = "none",
    receipt_role: str = ROLE_MEASUREMENT,
    timing: dict[str, Any] | None = None,
) -> GateReceipt:
    """Create a GateReceipt with proper content-addressed identity."""
    if receipt_role not in VALID_RECEIPT_ROLES:
        raise ValueError(
            f"Invalid receipt_role {receipt_role!r}; "
            f"must be one of {sorted(VALID_RECEIPT_ROLES)}"
        )
    if verdict not in VALID_VERDICTS:
        raise ValueError(
            f"Invalid verdict {verdict!r}; "
            f"must be one of {sorted(VALID_VERDICTS)}"
        )
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    s_hash = subject_hash(subject_kind, subject_bytes)
    e_hash = content_hash(canonical_json(evidence_bundle))
    p_hash = policy_hash(gate_config)
    rid = _compute_receipt_id(
        RECEIPT_SCHEMA_VERSION, gate, s_hash, e_hash, p_hash, receipt_role,
    )
    return GateReceipt(
        receipt_id=rid,
        schema_version=RECEIPT_SCHEMA_VERSION,
        timestamp=ts,
        gate=gate,
        verdict=verdict,
        subject_hash=s_hash,
        evidence_hash=e_hash,
        policy_hash=p_hash,
        principal_id=principal_id,
        tenant_id=tenant_id,
        auth_method=auth_method,
        receipt_role=receipt_role,
        timing=timing,
    )


# =============================================================================
# Evidence Store (content-addressed blob storage)
# =============================================================================


class EvidenceStore:
    """Content-addressed blob store for evidence bundles.

    Layout:
        {root}/evidence/{hash[:2]}/{hash}.json

    Same evidence_hash → same file → automatic dedup.
    """

    def __init__(self, root: Path):
        self.root = root / "evidence"
        self.root.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, evidence_hash: str) -> Path:
        return self.root / evidence_hash[:2] / f"{evidence_hash}.json"

    def put(self, bundle: dict[str, Any]) -> str:
        """Store evidence bundle, return its content hash."""
        blob = canonical_json(bundle)
        h = content_hash(blob)
        path = self._blob_path(h)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        return h

    def get(self, evidence_hash: str) -> dict[str, Any] | None:
        """Retrieve evidence bundle by hash, or None."""
        path = self._blob_path(evidence_hash)
        if not path.exists():
            return None
        return json.loads(path.read_bytes())

    def has(self, evidence_hash: str) -> bool:
        return self._blob_path(evidence_hash).exists()


# =============================================================================
# Receipt Store (append-only JSONL)
# =============================================================================


class ReceiptStore:
    """Append-only JSONL store for gate receipts.

    Layout:
        {root}/receipts/gate_receipts.jsonl

    Receipt rows are tiny (one line each).  Evidence lives in EvidenceStore.
    """

    def __init__(self, root: Path):
        self.dir = root / "receipts"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "gate_receipts.jsonl"

    def append(self, receipt: GateReceipt) -> None:
        """Append a receipt to the log."""
        with open(self.path, "a") as f:
            f.write(receipt.to_json() + "\n")

    def all(self) -> list[GateReceipt]:
        """Read all receipts (oldest first)."""
        if not self.path.exists():
            return []
        receipts = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                receipts.append(GateReceipt.from_dict(json.loads(line)))
        return receipts

    def query(
        self,
        gate: str | None = None,
        verdict: str | None = None,
        limit: int | None = None,
    ) -> list[GateReceipt]:
        """Query receipts with optional filters, newest first."""
        results = self.all()
        results.reverse()  # newest first
        if gate:
            results = [r for r in results if r.gate == gate]
        if verdict:
            results = [r for r in results if r.verdict == verdict]
        if limit and limit > 0:
            results = results[:limit]
        return results

    def get_by_id(self, receipt_id: str) -> GateReceipt | None:
        """Lookup a specific receipt by its content-addressed ID."""
        for receipt in self.all():
            if receipt.receipt_id == receipt_id:
                return receipt
        return None


# =============================================================================
# Combined Gate Receipt System
# =============================================================================


class GateReceiptSystem:
    """Combined receipt + evidence store for a governor directory.

    Usage:
        system = GateReceiptSystem(gov_dir)
        receipt = system.emit(
            gate="evidence_gate",
            verdict="block",
            subject_kind="text",
            subject_bytes=b"agent output here",
            evidence_bundle={"claims": [...], "blocking_reasons": [...]},
            gate_config={"strict": True, ...},
        )
        # Later:
        evidence = system.evidence_for(receipt)
    """

    def __init__(self, root: Path):
        self.receipt_store = ReceiptStore(root)
        self.evidence_store = EvidenceStore(root)

    def emit(
        self,
        gate: str,
        verdict: str,
        subject_kind: str,
        subject_bytes: bytes,
        evidence_bundle: dict[str, Any],
        gate_config: dict[str, Any],
        timestamp: str | None = None,
        principal_id: str = "local",
        tenant_id: str = "default",
        auth_method: str = "none",
        receipt_role: str = ROLE_MEASUREMENT,
    ) -> GateReceipt:
        """Create receipt, store evidence, append receipt to log."""
        # Store evidence blob (deduped by content)
        self.evidence_store.put(evidence_bundle)
        # Create receipt
        receipt = create_receipt(
            gate=gate,
            verdict=verdict,
            subject_kind=subject_kind,
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config=gate_config,
            timestamp=timestamp,
            principal_id=principal_id,
            tenant_id=tenant_id,
            auth_method=auth_method,
            receipt_role=receipt_role,
        )
        # Append to log
        self.receipt_store.append(receipt)
        return receipt

    def evidence_for(self, receipt: GateReceipt) -> dict[str, Any] | None:
        """Retrieve the evidence bundle for a receipt."""
        return self.evidence_store.get(receipt.evidence_hash)

    def query(
        self,
        gate: str | None = None,
        verdict: str | None = None,
        limit: int | None = None,
    ) -> list[GateReceipt]:
        return self.receipt_store.query(gate=gate, verdict=verdict, limit=limit)
