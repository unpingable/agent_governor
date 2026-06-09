# SPDX-License-Identifier: Apache-2.0
"""
Gate Receipt: content-addressed decision receipts for governor gates.

Every gate (evidence gate, pre-commit, wrapper, etc.) emits a GateReceipt
after checking a subject. Receipts are append-only, content-addressed,
and queryable.

Design choices (informed by ChatGPT review):
- receipt_id = H(schema_version + gate + subject_hash + evidence_hash + policy_hash + receipt_role
                 [+ horizon_hash if present] [+ unsettled_hash if non-empty])
  This is truly content-addressed: same policy + same subject + same evidence + same role
  + same unsettled set = same receipt_id.  Timestamp is metadata, not identity.  receipt_role is
  included because role changes semantics — a measurement and a reset with the same payload are
  different.  unsettled distinguishes what a verdict permits from what it leaves unsettled
  (v4 onward); two receipts with the same payload but different unsettled claims are different
  decisions.
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
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =============================================================================
# Schema
# =============================================================================

RECEIPT_SCHEMA_VERSION = 4


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
# Tolerability Horizon (GOV_GAP_TOLERABILITY_HORIZON_001)
# =============================================================================
#
# Horizon answers "how long is this adverse condition acceptable?" —
# orthogonal to verdict, which answers "what should happen right now?"
# The enum is frozen v1; widening requires a gap-spec supersession.

HORIZON_NONE = "none"
HORIZON_NOW = "now"
HORIZON_HOURS = "hours"
HORIZON_BUSINESS_HOURS = "business_hours"
HORIZON_SCHEDULED = "scheduled"
HORIZON_OBSERVE_ONLY = "observe_only"
HORIZON_INDEFINITE = "indefinite"

VALID_HORIZON_KINDS = frozenset({
    HORIZON_NONE, HORIZON_NOW, HORIZON_HOURS,
    HORIZON_BUSINESS_HOURS, HORIZON_SCHEDULED,
    HORIZON_OBSERVE_ONLY, HORIZON_INDEFINITE,
})

# Horizons that require a wall-clock expiry. Past expiry, consumers
# must re-escalate to HORIZON_NOW until the receipt is re-emitted.
HORIZON_EXPIRY_REQUIRED = frozenset({
    HORIZON_HOURS, HORIZON_BUSINESS_HOURS, HORIZON_SCHEDULED,
})

# Horizons that create a consumer persistence obligation for stateful
# multi-run consumers (A5 per spec). Same set as EXPIRY_REQUIRED —
# deferred tolerance with a clock needs lineage across runs.
HORIZON_DEFERRAL_PERSISTENCE_OBLIGED = HORIZON_EXPIRY_REQUIRED


@dataclass(frozen=True)
class HorizonBlock:
    """Tolerability horizon on a gate receipt.

    The four fields encode a declaration that carries across runs:

        kind         — one of VALID_HORIZON_KINDS
        basis_id     — policy / declaration / override id that authorizes
                       the tolerance. Required for non-'none'.
        basis_hash   — content hash of the basis artifact, format
                       'sha256:<64 hex chars>'. Required for non-'none'.
                       Same discipline as standing receipt parent refs
                       (see governor.standing.types.is_valid_content_hash).
        expiry       — ISO 8601 UTC timestamp. Required for 'hours',
                       'business_hours', 'scheduled'. Optional for
                       'observe_only' and 'indefinite' (no clock).

    Invariants:
    - Horizon is declared, never inferred from verdict or severity.
    - Missing field != zero. Absent HorizonBlock means "producer did
      not declare"; consumer policy decides fail-open vs fail-closed.
    - Horizon is content-bound to its basis: if the basis artifact
      changes, the basis_hash diverges on re-read and the receipt is
      treated as basis_invalidated.
    """

    kind: str
    basis_id: str | None = None
    basis_hash: str | None = None
    expiry: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in VALID_HORIZON_KINDS:
            raise ValueError(
                f"Invalid horizon kind {self.kind!r}; "
                f"must be one of {sorted(VALID_HORIZON_KINDS)}"
            )
        if self.kind != HORIZON_NONE:
            if not self.basis_id:
                raise ValueError(
                    f"Horizon {self.kind!r} requires basis_id "
                    "(non-'none' horizon without basis is a schema violation)"
                )
            if not self.basis_hash:
                raise ValueError(
                    f"Horizon {self.kind!r} requires basis_hash "
                    "(non-'none' horizon without basis is a schema violation)"
                )
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.basis_hash):
                raise ValueError(
                    "basis_hash must match 'sha256:<64 hex chars>', "
                    f"got {self.basis_hash!r}"
                )
        else:
            # 'none' horizon must not carry basis or expiry — presence
            # would misrepresent a non-declaration as a declaration.
            if self.basis_id is not None or self.basis_hash is not None:
                raise ValueError(
                    "Horizon 'none' must not carry basis_id/basis_hash; "
                    "missing != declared-none."
                )
            if self.expiry is not None:
                raise ValueError(
                    "Horizon 'none' must not carry expiry."
                )
        if self.kind in HORIZON_EXPIRY_REQUIRED:
            if not self.expiry:
                raise ValueError(
                    f"Horizon {self.kind!r} requires expiry "
                    "(clock-bounded horizon without expiry is a schema violation)"
                )
        if self.expiry is not None:
            try:
                # Accept 'Z' suffix and explicit offset both.
                datetime.fromisoformat(self.expiry.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(
                    f"expiry must be ISO 8601, got {self.expiry!r}"
                ) from exc

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        if self.basis_id is not None:
            d["basis_id"] = self.basis_id
        if self.basis_hash is not None:
            d["basis_hash"] = self.basis_hash
        if self.expiry is not None:
            d["expiry"] = self.expiry
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HorizonBlock:
        return cls(
            kind=data["kind"],
            basis_id=data.get("basis_id"),
            basis_hash=data.get("basis_hash"),
            expiry=data.get("expiry"),
        )

    def content_hash(self) -> str:
        """Hash the horizon block for receipt_id binding.

        Included in receipt_id only when horizon is present. Absent
        horizon leaves receipt_id computation unchanged (backward
        compatibility).
        """
        return content_hash(canonical_json(self.to_dict()))


# =============================================================================
# Non-discharge: what a verdict explicitly leaves unsettled (v4)
# =============================================================================
#
# A gate receipt's verdict records what was permitted/denied. The unsettled
# field records what the verdict explicitly did NOT settle. Without it, a
# permit receipt is indistinguishable from a permit that also discharged
# upstream claims it never inspected. The vocabulary is closed: adding a
# new kind requires ratification, not an ad-hoc string. The freeform
# `reason` field is prose-for-humans and does not participate in matching
# or dispatch.

UNSETTLED_AUTHORITY = "authority"
UNSETTLED_EVIDENCE_SUFFICIENCY = "evidence_sufficiency"
UNSETTLED_FRESHNESS = "freshness"
UNSETTLED_SCOPE = "scope"
UNSETTLED_STANDING = "standing"
UNSETTLED_CONSUMER_RELIANCE = "consumer_reliance"

VALID_NON_DISCHARGE_KINDS = frozenset({
    UNSETTLED_AUTHORITY, UNSETTLED_EVIDENCE_SUFFICIENCY,
    UNSETTLED_FRESHNESS, UNSETTLED_SCOPE,
    UNSETTLED_STANDING, UNSETTLED_CONSUMER_RELIANCE,
})


@dataclass(frozen=True)
class NonDischargeClaim:
    """One thing this verdict explicitly does NOT settle.

    Fields:
        kind                 — closed enum (VALID_NON_DISCHARGE_KINDS).
                               New kinds require ratification, not an
                               ad-hoc string. C4 discipline.
        reason               — freeform prose for human reviewers. Does
                               not participate in matching or dispatch.
        required_consumer    — optional repo-local identifier of the
                               consumer that would need to discharge
                               this claim downstream.
        required_witness     — optional repo-local identifier of a
                               witness that would discharge it.

    Both optional fields are kept as freeform strings deliberately. They
    are most likely to be repo-local identifiers at first contact; typing
    them prematurely is cathedralization.
    """

    kind: str
    reason: str
    required_consumer: str | None = None
    required_witness: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in VALID_NON_DISCHARGE_KINDS:
            raise ValueError(
                f"Invalid non-discharge kind {self.kind!r}; "
                f"must be one of {sorted(VALID_NON_DISCHARGE_KINDS)}"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "reason": self.reason}
        if self.required_consumer is not None:
            d["required_consumer"] = self.required_consumer
        if self.required_witness is not None:
            d["required_witness"] = self.required_witness
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NonDischargeClaim:
        return cls(
            kind=data["kind"],
            reason=data["reason"],
            required_consumer=data.get("required_consumer"),
            required_witness=data.get("required_witness"),
        )


# =============================================================================
# Canonicalization
# =============================================================================


def canonical_json(obj: dict[str, Any] | list[Any]) -> bytes:
    """Deterministic JSON: sorted keys, compact separators, ASCII-safe.

    This is the canonical form used for all hashing.  Do not change
    the parameters without bumping RECEIPT_SCHEMA_VERSION.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
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
    horizon_hash: str | None = None,
    unsettled_hash: str | None = None,
) -> str:
    """Content-addressed receipt identity.

    Same policy + same subject + same evidence + same role = same receipt_id.
    Timestamp is deliberately excluded — it's metadata, not identity.
    receipt_role is included because role changes semantics — two receipts with
    the same payload but different roles are not the same thing.

    horizon_hash binds the horizon block into identity when present. A receipt
    with horizon=hours/expiry=T1 and a receipt with horizon=hours/expiry=T2
    make different semantic claims and must not collide. Absent horizon_hash
    preserves pre-horizon receipt_id computation (backward compatibility) —
    the ":horizon:" fragment is omitted entirely, not appended as empty.

    unsettled_hash binds the unsettled non-discharge set into identity when
    non-empty. Two v4 receipts with the same payload but different unsettled
    claims are different decisions. Absent or empty unsettled preserves the
    pre-unsettled receipt_id computation — the ":unsettled:" fragment is
    omitted entirely, mirroring the horizon pattern.
    """
    payload = f"{schema_version}:{gate}:{s_hash}:{e_hash}:{p_hash}:{receipt_role}"
    if horizon_hash is not None:
        payload += f":horizon:{horizon_hash}"
    if unsettled_hash is not None:
        payload += f":unsettled:{unsettled_hash}"
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

    principal_ref is a content-addressed hash of the authenticated principal,
    format ``sha256:<64 hex chars>``.  Null in v2 — placeholder for v3 crypto
    binding.  NOT part of receipt_id.

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
    principal_ref: str | None = None
    horizon: HorizonBlock | None = None
    unsettled: tuple[NonDischargeClaim, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(
                f"Invalid verdict {self.verdict!r}; "
                f"must be one of {sorted(VALID_VERDICTS)}"
            )
        if self.principal_ref is not None:
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.principal_ref):
                raise ValueError(
                    f"principal_ref must match 'sha256:<64 hex chars>', "
                    f"got {self.principal_ref!r}"
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
        if self.principal_ref is not None:
            d["principal_ref"] = self.principal_ref
        # horizon omitted when None — preserves pre-horizon receipt shape
        # and leaves canonical_json stable for receipts without a horizon
        # declaration. Missing != declared-none.
        if self.horizon is not None:
            d["horizon"] = self.horizon.to_dict()
        # unsettled emitted only for v4+ receipts. A v3 receipt loaded from
        # disk retains schema_version=3 and serializes without `unsettled`,
        # preserving byte-stable roundtrip for legacy receipts. v4 receipts
        # always emit `unsettled` (possibly empty) — the empty list is a
        # positive claim "no unsettled claims surfaced," not silence.
        # Legacy v1 receipts may carry schema_version as a string
        # ("receipt_v1"); those are by definition pre-v4 and skipped.
        if isinstance(self.schema_version, int) and self.schema_version >= 4:
            d["unsettled"] = [c.to_dict() for c in self.unsettled]
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
        horizon_data = data.get("horizon")
        horizon = HorizonBlock.from_dict(horizon_data) if horizon_data else None
        # v3 receipts have no `unsettled` field — default to empty tuple.
        # v4 receipts have `unsettled: []` or a list of claim dicts.
        unsettled_raw = data.get("unsettled", ())
        unsettled = tuple(
            NonDischargeClaim.from_dict(c) for c in unsettled_raw
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
            principal_ref=data.get("principal_ref"),
            horizon=horizon,
            unsettled=unsettled,
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
    principal_ref: str | None = None,
    horizon: HorizonBlock | None = None,
    unsettled: tuple[NonDischargeClaim, ...] = (),
) -> GateReceipt:
    """Create a GateReceipt with proper content-addressed identity.

    horizon is optional. When present, it binds into receipt_id so two
    receipts with identical subject/evidence/policy/role but different
    tolerability horizons are distinct claims.

    unsettled is the list of typed non-discharge claims the verdict
    explicitly leaves open. Empty by default. When non-empty, it binds
    into receipt_id so two receipts with otherwise-identical fields but
    different unsettled sets are distinct decisions.
    """
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
    # Empty unsettled does NOT bind into receipt_id (matches horizon pattern).
    # Non-empty unsettled hashes its canonical-json item list.
    unsettled_hash = (
        content_hash(canonical_json([c.to_dict() for c in unsettled]))
        if unsettled
        else None
    )
    rid = _compute_receipt_id(
        RECEIPT_SCHEMA_VERSION, gate, s_hash, e_hash, p_hash, receipt_role,
        horizon_hash=horizon.content_hash() if horizon is not None else None,
        unsettled_hash=unsettled_hash,
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
        principal_ref=principal_ref,
        horizon=horizon,
        unsettled=unsettled,
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
        timing: dict[str, Any] | None = None,
        principal_ref: str | None = None,
        horizon: HorizonBlock | None = None,
        unsettled: tuple[NonDischargeClaim, ...] = (),
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
            timing=timing,
            principal_ref=principal_ref,
            horizon=horizon,
            unsettled=unsettled,
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
