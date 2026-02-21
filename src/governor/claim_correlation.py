# SPDX-License-Identifier: Apache-2.0
"""
Claim↔Receipt Correlation Layer.

Lightweight claim records, receipt linkage, and verification status derivation.
Status is a **derived view** over linked receipts and receipt-chain validity,
not a standalone source of truth.

Design:
- ClaimRecord is lightweight (not GroundedClaim) — persistent but cheap
- JSONL persistence matches gate_receipt pattern (append-only, write-locked)
- Verification status derived mechanically from linked receipts (no heuristics)
- Linkage is external: junction store (claims.jsonl + links.jsonl), NOT embedded
  in GateReceipt (would change identity hash). Receipts are not modified.
- Idempotent: deterministic claim_key prevents duplicates on replays;
  link_receipt deduplicates by (claim_id, receipt_id, role) triple
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum length for claim text (truncated on mint, fingerprint from full text)
MAX_CLAIM_TEXT = 500


# =============================================================================
# Verification Status (derived, not authoritative)
# =============================================================================


class ClaimVerificationStatus(str, Enum):
    """Derived verification status for a claim."""

    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"


# =============================================================================
# Data Model
# =============================================================================


def _sha256(text: str) -> str:
    """SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compute_claim_key(
    source_gate: str,
    run_id: str | None,
    normalized_text: str,
    level: str,
) -> str:
    """Deterministic fingerprint for idempotency.

    Same gate + run + text + level = same claim_key.
    """
    parts = f"{source_gate}\x00{run_id or ''}\x00{normalized_text}\x00{level}"
    return _sha256(parts)


def _compute_claim_fingerprint(normalized_text: str) -> str:
    """Text identity across contexts."""
    return _sha256(normalized_text)


def _normalize_text(text: str) -> str:
    """Normalize claim text for fingerprinting.

    Strip whitespace and lowercase for stable identity.
    """
    return " ".join(text.lower().split())


def _utc_now() -> str:
    """UTC ISO 8601 timestamp — single clock for all minting."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso_timestamp(s: str) -> datetime:
    """Parse ISO 8601 timestamp, handling naive→UTC.

    Raises ValueError on unparseable input.
    """
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class ClaimRecord:
    """A lightweight claim extracted from agent output.

    Persistent, content-addressed by claim_key for idempotency.
    """

    claim_id: str
    claim_key: str
    claim_kind: str          # "evidence_gate" | "chat_assertion" | "manual"
    claim_text: str          # human-readable (truncated to MAX_CLAIM_TEXT)
    claim_level: str         # "hard" | "soft"
    claim_fingerprint: str   # H(normalized_text)
    run_id: str | None = None
    task_id: str | None = None
    step_id: str | None = None
    source_gate: str = "evidence_gate"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_key": self.claim_key,
            "claim_kind": self.claim_kind,
            "claim_text": self.claim_text,
            "claim_level": self.claim_level,
            "claim_fingerprint": self.claim_fingerprint,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "source_gate": self.source_gate,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClaimRecord:
        return cls(
            claim_id=data["claim_id"],
            claim_key=data["claim_key"],
            claim_kind=data["claim_kind"],
            claim_text=data["claim_text"],
            claim_level=data["claim_level"],
            claim_fingerprint=data["claim_fingerprint"],
            run_id=data.get("run_id"),
            task_id=data.get("task_id"),
            step_id=data.get("step_id"),
            source_gate=data.get("source_gate", "evidence_gate"),
            created_at=data.get("created_at", ""),
        )


@dataclass(frozen=True)
class ReceiptLink:
    """Junction between a claim and a receipt.

    Role semantics:
    - "supports": receipt verdict is "pass" or "warn" for this claim
    - "contradicts": receipt conflicts with this claim (verdict "block" or explicit)
    - "neutral": receipt is related but doesn't speak to this claim's truth
    """

    link_id: str
    claim_id: str
    receipt_id: str
    role: str  # "supports" | "contradicts" | "neutral"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "claim_id": self.claim_id,
            "receipt_id": self.receipt_id,
            "role": self.role,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReceiptLink:
        return cls(
            link_id=data["link_id"],
            claim_id=data["claim_id"],
            receipt_id=data["receipt_id"],
            role=data["role"],
            created_at=data.get("created_at", ""),
        )


VALID_LINK_ROLES = frozenset({"supports", "contradicts", "neutral"})


# =============================================================================
# Verification Summary (returned to UI)
# =============================================================================


@dataclass
class ClaimVerificationSummary:
    """Complete verification view for a single claim. Returned to UI."""

    schema: str = "claim_verification_summary.v1"
    claim_id: str = ""
    claim_kind: str = ""
    claim_text: str = ""
    claim_level: str = ""
    claim_fingerprint: str = ""
    status: ClaimVerificationStatus = ClaimVerificationStatus.UNVERIFIED
    supporting_receipt_ids: list[str] = field(default_factory=list)
    contradicting_receipt_ids: list[str] = field(default_factory=list)
    neutral_receipt_ids: list[str] = field(default_factory=list)
    unresolved_receipt_refs: int = 0
    receipt_chain_ok: bool = True
    run_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "claim_id": self.claim_id,
            "claim_kind": self.claim_kind,
            "claim_text": self.claim_text,
            "claim_level": self.claim_level,
            "claim_fingerprint": self.claim_fingerprint,
            "status": self.status.value if isinstance(self.status, ClaimVerificationStatus) else self.status,
            "supporting_receipt_ids": self.supporting_receipt_ids,
            "contradicting_receipt_ids": self.contradicting_receipt_ids,
            "neutral_receipt_ids": self.neutral_receipt_ids,
            "unresolved_receipt_refs": self.unresolved_receipt_refs,
            "receipt_chain_ok": self.receipt_chain_ok,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# =============================================================================
# Receipt verdict helper
# =============================================================================


def receipt_verdict(receipt: Any) -> str:
    """Canonical verdict extraction. All derivation goes through here.

    Accepts anything with a .verdict attribute (GateReceipt, dict, etc.).
    """
    if isinstance(receipt, dict):
        v = receipt.get("verdict", "unknown")
    else:
        v = getattr(receipt, "verdict", "unknown")
    v = str(v).lower()
    if v in ("pass", "warn", "block"):
        return v
    return "unknown"


# =============================================================================
# Derivation Logic (pure function)
# =============================================================================


def derive_status(
    links: list[ReceiptLink],
    receipts: dict[str, Any | None],
    chain_ok: bool = True,
) -> tuple[ClaimVerificationStatus, int]:
    """Derive verification status from linked receipts.

    Args:
        links: Receipt links for a single claim
        receipts: Mapping of receipt_id → receipt object (or None if unresolved)
        chain_ok: Whether the receipt chain is valid

    Returns:
        (status, unresolved_count)

    Rules (in priority order):
    1. Any link with role="contradicts" (and receipt resolves) → CONTRADICTED
    2. Any resolved linked receipt with verdict="block" → CONTRADICTED
    3. No links → UNVERIFIED
    4. Count unresolved: linked receipt_ids that don't resolve
    5. At least one role="supports" with resolved verdict="pass" AND chain_ok → VERIFIED
    6. Supporting receipts exist but chain_ok=False → PARTIAL
    7. Otherwise → PARTIAL
    """
    if not links:
        return ClaimVerificationStatus.UNVERIFIED, 0

    unresolved = 0
    has_supports_pass = False
    has_any_supports = False

    for link in links:
        r = receipts.get(link.receipt_id)
        if r is None:
            unresolved += 1
            continue

        v = receipt_verdict(r)

        # Rule 1: explicit contradiction role
        if link.role == "contradicts":
            return ClaimVerificationStatus.CONTRADICTED, unresolved

        # Rule 2: block verdict on any linked receipt
        if v == "block":
            return ClaimVerificationStatus.CONTRADICTED, unresolved

        if link.role == "supports":
            has_any_supports = True
            if v == "pass":
                has_supports_pass = True

    # Rule 5: verified if supporting pass + chain ok
    if has_supports_pass and chain_ok:
        return ClaimVerificationStatus.VERIFIED, unresolved

    # Rule 6: supporting but bad chain
    if has_supports_pass and not chain_ok:
        return ClaimVerificationStatus.PARTIAL, unresolved

    # Rule 7: has some supports (warn-only or unresolved mix)
    if has_any_supports:
        return ClaimVerificationStatus.PARTIAL, unresolved

    # Fallback: links exist but none supporting
    return ClaimVerificationStatus.PARTIAL, unresolved


# =============================================================================
# Correlation Context
# =============================================================================


@dataclass
class CorrelationContext:
    """Passed to gates that should mint claims. Keeps the call site clean."""

    claim_store: ClaimCorrelationStore
    run_id: str | None = None
    task_id: str | None = None
    step_id: str | None = None
    source_gate: str = "evidence_gate"


# =============================================================================
# Window Result
# =============================================================================


@dataclass
class WindowResult:
    """Time-window bundle for Guvnah timeline."""

    schema: str = "claims_window.v1"
    claims: list[ClaimVerificationSummary] = field(default_factory=list)
    receipt_stubs: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    counts_by_status: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "claims": [c.to_dict() for c in self.claims],
            "receipt_stubs": self.receipt_stubs,
            "count": self.count,
            "counts_by_status": self.counts_by_status,
        }


# =============================================================================
# Persistence Store
# =============================================================================


class ClaimCorrelationStore:
    """JSONL-backed claim↔receipt correlation store.

    Append-only with process-local write lock.
    Layout:
        {gov_dir}/claims/claims.jsonl
        {gov_dir}/claims/links.jsonl
    """

    def __init__(self, gov_dir: Path) -> None:
        self._dir = gov_dir / "claims"
        self._claims_path = self._dir / "claims.jsonl"
        self._links_path = self._dir / "links.jsonl"
        self._lock = threading.Lock()

        # In-memory indexes
        self._claims: dict[str, ClaimRecord] = {}           # claim_id → record
        self._claims_by_key: dict[str, str] = {}            # claim_key → claim_id
        self._links: dict[str, ReceiptLink] = {}            # link_id → link
        self._links_by_claim: dict[str, list[str]] = {}     # claim_id → [link_id]
        self._links_by_receipt: dict[str, list[str]] = {}   # receipt_id → [link_id]
        # Dedup set: (claim_id, receipt_id, role)
        self._link_triples: set[tuple[str, str, str]] = set()

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _append_claim(self, record: ClaimRecord) -> None:
        """Append a claim record to JSONL (caller holds lock)."""
        self._ensure_dir()
        with open(self._claims_path, "a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
            f.flush()

    def _append_link(self, link: ReceiptLink) -> None:
        """Append a link record to JSONL (caller holds lock)."""
        self._ensure_dir()
        with open(self._links_path, "a") as f:
            f.write(json.dumps(link.to_dict()) + "\n")
            f.flush()

    def mint_claim(
        self,
        kind: str,
        text: str,
        level: str,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        step_id: str | None = None,
        source_gate: str = "evidence_gate",
    ) -> ClaimRecord:
        """Mint a claim record. Idempotent: returns existing if claim_key matches."""
        normalized = _normalize_text(text)
        key = _compute_claim_key(source_gate, run_id, normalized, level)

        with self._lock:
            # Check for existing
            existing_id = self._claims_by_key.get(key)
            if existing_id is not None:
                return self._claims[existing_id]

            fingerprint = _compute_claim_fingerprint(normalized)
            claim_id = uuid.uuid4().hex
            now = _utc_now()

            record = ClaimRecord(
                claim_id=claim_id,
                claim_key=key,
                claim_kind=kind,
                claim_text=text[:MAX_CLAIM_TEXT],
                claim_level=level.lower(),
                claim_fingerprint=fingerprint,
                run_id=run_id,
                task_id=task_id,
                step_id=step_id,
                source_gate=source_gate,
                created_at=now,
            )

            # Index
            self._claims[claim_id] = record
            self._claims_by_key[key] = claim_id

            # Persist
            self._append_claim(record)

            return record

    def link_receipt(
        self,
        claim_id: str,
        receipt_id: str,
        role: str = "supports",
    ) -> ReceiptLink:
        """Link a receipt to a claim. Idempotent: no-op if triple exists."""
        if role not in VALID_LINK_ROLES:
            raise ValueError(f"Invalid role {role!r}; must be one of {sorted(VALID_LINK_ROLES)}")

        with self._lock:
            triple = (claim_id, receipt_id, role)
            # Check for existing
            if triple in self._link_triples:
                # Find and return existing link
                for lid in self._links_by_claim.get(claim_id, []):
                    link = self._links[lid]
                    if link.receipt_id == receipt_id and link.role == role:
                        return link

            link_id = uuid.uuid4().hex
            now = _utc_now()

            link = ReceiptLink(
                link_id=link_id,
                claim_id=claim_id,
                receipt_id=receipt_id,
                role=role,
                created_at=now,
            )

            # Index
            self._links[link_id] = link
            self._links_by_claim.setdefault(claim_id, []).append(link_id)
            self._links_by_receipt.setdefault(receipt_id, []).append(link_id)
            self._link_triples.add(triple)

            # Persist
            self._append_link(link)

            return link

    def get_claim(self, claim_id: str) -> ClaimRecord | None:
        """Get a claim by ID."""
        return self._claims.get(claim_id)

    def get_links(self, claim_id: str) -> list[ReceiptLink]:
        """Get links for a claim (oldest first — causal order)."""
        link_ids = self._links_by_claim.get(claim_id, [])
        links = [self._links[lid] for lid in link_ids]
        links.sort(key=lambda l: l.created_at)
        return links

    def get_claims_for_receipt(self, receipt_id: str) -> list[ClaimRecord]:
        """Reverse lookup: which claims does a receipt relate to?"""
        link_ids = self._links_by_receipt.get(receipt_id, [])
        claim_ids = set()
        for lid in link_ids:
            claim_ids.add(self._links[lid].claim_id)
        return [self._claims[cid] for cid in claim_ids if cid in self._claims]

    def list_claims(
        self,
        *,
        run_id: str | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[ClaimRecord]:
        """List claims, newest first."""
        claims = list(self._claims.values())

        if run_id is not None:
            claims = [c for c in claims if c.run_id == run_id]

        if since is not None:
            since_dt = parse_iso_timestamp(since)
            claims = [
                c for c in claims
                if c.created_at and parse_iso_timestamp(c.created_at) >= since_dt
            ]

        # Sort: newest first
        claims.sort(key=lambda c: c.created_at, reverse=True)

        if limit > 0:
            claims = claims[:limit]

        return claims

    def summarize(
        self,
        claim_id: str,
        receipt_system: Any = None,
    ) -> ClaimVerificationSummary | None:
        """Build a verification summary for a claim."""
        claim = self.get_claim(claim_id)
        if claim is None:
            return None

        links = self.get_links(claim_id)

        # Resolve receipts
        receipts: dict[str, Any | None] = {}
        for link in links:
            if receipt_system is not None:
                try:
                    r = receipt_system.receipt_store.get_by_id(link.receipt_id)
                    receipts[link.receipt_id] = r
                except Exception:
                    receipts[link.receipt_id] = None
            else:
                receipts[link.receipt_id] = None

        # Derive status
        chain_ok = True  # TODO: wire chain verification in v2
        status, unresolved = derive_status(links, receipts, chain_ok)

        # Classify receipt IDs by role
        supporting = [l.receipt_id for l in links if l.role == "supports"]
        contradicting = [l.receipt_id for l in links if l.role == "contradicts"]
        neutral = [l.receipt_id for l in links if l.role == "neutral"]

        # Most recent link timestamp
        updated_at = max((l.created_at for l in links), default=claim.created_at)

        return ClaimVerificationSummary(
            claim_id=claim.claim_id,
            claim_kind=claim.claim_kind,
            claim_text=claim.claim_text,
            claim_level=claim.claim_level,
            claim_fingerprint=claim.claim_fingerprint,
            status=status,
            supporting_receipt_ids=supporting,
            contradicting_receipt_ids=contradicting,
            neutral_receipt_ids=neutral,
            unresolved_receipt_refs=unresolved,
            receipt_chain_ok=chain_ok,
            run_id=claim.run_id,
            created_at=claim.created_at,
            updated_at=updated_at,
        )

    def window(
        self,
        since: str,
        until: str | None = None,
        receipt_system: Any = None,
        *,
        limit: int = 50,
    ) -> WindowResult:
        """Time-window bundle for Guvnah timeline."""
        since_dt = parse_iso_timestamp(since)
        until_dt = parse_iso_timestamp(until) if until else None

        # Filter claims by time window
        claims = list(self._claims.values())
        filtered = []
        for c in claims:
            if not c.created_at:
                continue
            ct = parse_iso_timestamp(c.created_at)
            if ct < since_dt:
                continue
            if until_dt and ct > until_dt:
                continue
            filtered.append(c)

        # Sort: newest first
        filtered.sort(key=lambda c: c.created_at, reverse=True)
        if limit > 0:
            filtered = filtered[:limit]

        # Build summaries
        summaries = []
        all_receipt_ids: set[str] = set()
        for claim in filtered:
            summary = self.summarize(claim.claim_id, receipt_system)
            if summary:
                summaries.append(summary)
                all_receipt_ids.update(summary.supporting_receipt_ids)
                all_receipt_ids.update(summary.contradicting_receipt_ids)
                all_receipt_ids.update(summary.neutral_receipt_ids)

        # Build receipt stubs (oldest first)
        stubs: list[dict[str, Any]] = []
        if receipt_system is not None:
            for rid in sorted(all_receipt_ids):
                try:
                    r = receipt_system.receipt_store.get_by_id(rid)
                    if r is not None:
                        stubs.append({
                            "receipt_id": r.receipt_id,
                            "timestamp": r.timestamp,
                            "verdict": r.verdict,
                            "gate": r.gate,
                        })
                except Exception:
                    pass

        # Count by status
        counts: dict[str, int] = {}
        for s in summaries:
            sv = s.status.value if isinstance(s.status, ClaimVerificationStatus) else s.status
            counts[sv] = counts.get(sv, 0) + 1

        return WindowResult(
            claims=summaries,
            receipt_stubs=stubs,
            count=len(summaries),
            counts_by_status=counts,
        )

    def stats(self) -> dict[str, Any]:
        """Quick rollup for top-card."""
        claims = list(self._claims.values())
        total = len(claims)
        newest_at = max((c.created_at for c in claims), default="")

        # Count by status would require summarizing each claim,
        # which needs receipt_system. Return structural counts instead.
        counts_by_level: dict[str, int] = {}
        for c in claims:
            counts_by_level[c.claim_level] = counts_by_level.get(c.claim_level, 0) + 1

        return {
            "total": total,
            "counts_by_level": counts_by_level,
            "total_links": len(self._links),
            "newest_at": newest_at,
        }

    @classmethod
    def load(cls, gov_dir: Path) -> ClaimCorrelationStore:
        """Load store from JSONL files.

        Resilient: skips blank/corrupt lines with warning log.
        """
        store = cls(gov_dir)
        claims_path = gov_dir / "claims" / "claims.jsonl"
        links_path = gov_dir / "claims" / "links.jsonl"

        # Load claims
        if claims_path.exists():
            for lineno, line in enumerate(claims_path.read_text().splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    record = ClaimRecord.from_dict(data)
                    store._claims[record.claim_id] = record
                    store._claims_by_key[record.claim_key] = record.claim_id
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning(
                        "claims.jsonl line %d: skipping corrupt record: %s", lineno, exc
                    )

        # Load links
        if links_path.exists():
            for lineno, line in enumerate(links_path.read_text().splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    link = ReceiptLink.from_dict(data)
                    store._links[link.link_id] = link
                    store._links_by_claim.setdefault(link.claim_id, []).append(link.link_id)
                    store._links_by_receipt.setdefault(link.receipt_id, []).append(link.link_id)
                    store._link_triples.add((link.claim_id, link.receipt_id, link.role))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning(
                        "links.jsonl line %d: skipping corrupt record: %s", lineno, exc
                    )

        return store
