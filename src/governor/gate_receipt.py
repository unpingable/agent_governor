"""
Gate Receipt: content-addressed decision receipts for governor gates.

Every gate (evidence gate, pre-commit, wrapper, etc.) emits a GateReceipt
after checking a subject. Receipts are append-only, content-addressed,
and queryable.

Design choices (informed by ChatGPT review):
- receipt_id = H(schema_version + gate + subject_hash + evidence_hash + policy_hash)
  This is truly content-addressed: same policy + same subject + same evidence
  = same receipt_id.  Timestamp is metadata, not identity.
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

RECEIPT_SCHEMA_VERSION = 1


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


def _compute_receipt_id(
    schema_version: int,
    gate: str,
    s_hash: str,
    e_hash: str,
    p_hash: str,
) -> str:
    """Content-addressed receipt identity.

    Same policy + same subject + same evidence = same receipt_id.
    Timestamp is deliberately excluded — it's metadata, not identity.
    """
    payload = f"{schema_version}:{gate}:{s_hash}:{e_hash}:{p_hash}"
    return content_hash(payload.encode("utf-8"))


# =============================================================================
# GateReceipt
# =============================================================================


@dataclass(frozen=True)
class GateReceipt:
    """A content-addressed decision receipt from a governor gate.

    Fields:
        receipt_id       H(schema_version + gate + subject_hash + evidence_hash + policy_hash)
        schema_version   Protocol version (bump on breaking changes)
        timestamp        ISO 8601 UTC — ordering metadata, NOT identity
        gate             Which gate produced this receipt
        verdict          "pass" | "warn" | "block"
        subject_hash     H(subject_kind + \\x00 + subject_bytes)
        evidence_hash    H(canonical_json(evidence_bundle))
        policy_hash      H(canonical_json(gate_config))
    """

    receipt_id: str
    schema_version: int
    timestamp: str
    gate: str
    verdict: str
    subject_hash: str
    evidence_hash: str
    policy_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "gate": self.gate,
            "verdict": self.verdict,
            "subject_hash": self.subject_hash,
            "evidence_hash": self.evidence_hash,
            "policy_hash": self.policy_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GateReceipt:
        return cls(
            receipt_id=data["receipt_id"],
            schema_version=data["schema_version"],
            timestamp=data["timestamp"],
            gate=data["gate"],
            verdict=data["verdict"],
            subject_hash=data["subject_hash"],
            evidence_hash=data["evidence_hash"],
            policy_hash=data["policy_hash"],
        )


def create_receipt(
    gate: str,
    verdict: str,
    subject_kind: str,
    subject_bytes: bytes,
    evidence_bundle: dict[str, Any],
    gate_config: dict[str, Any],
    timestamp: str | None = None,
) -> GateReceipt:
    """Create a GateReceipt with proper content-addressed identity."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    s_hash = subject_hash(subject_kind, subject_bytes)
    e_hash = content_hash(canonical_json(evidence_bundle))
    p_hash = policy_hash(gate_config)
    rid = _compute_receipt_id(
        RECEIPT_SCHEMA_VERSION, gate, s_hash, e_hash, p_hash,
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
