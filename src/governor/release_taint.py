# SPDX-License-Identifier: Apache-2.0
"""Release Taint — publish-boundary assessment for kernel runs.

Computes whether a kernel run's oracle evidence meets the minimum
independence class required for release/publish. This is a derived read
of existing kernel data, not a new invariant — no persistence, no state.

Tri-state status:
  "clean"   — all high-confidence oracle-backed claims meet publish threshold
  "tainted" — at least one high-confidence claim backed by below-threshold oracle
  "unknown" — missing data makes taint assessment impossible (unauditable)

UNKNOWN is the safe default. Missing claims_map, missing evidence blobs,
or missing oracle_class metadata all produce UNKNOWN — not clean.

Known simplifications (same as oracle.independence_minimum invariant):
- Max-class-over-all-oracles: highest class cited by a claim satisfies the
  requirement. A high-class but irrelevant oracle can satisfy a requirement
  intended for a different evidence type. Future: per-evidence-kind checks.
- Scope axis plumbed but not populated: claims don't carry scope today.
  When they do, no changes are needed here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaintReason:
    """One claim that fails the publish threshold."""

    claim_id: str
    observed_class: int
    publish_min_class: int

    @property
    def code(self) -> str:
        return f"weak_oracle_class_{self.observed_class}_below_{self.publish_min_class}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "observed_class": self.observed_class,
            "publish_min_class": self.publish_min_class,
            "code": self.code,
        }


@dataclass
class RunTaint:
    """Tri-state taint assessment for a kernel run.

    status:
      "clean"   — all high-confidence oracle-backed claims meet publish threshold
      "tainted" — at least one high-confidence claim backed by below-threshold oracle
      "unknown" — missing data makes taint assessment impossible (unauditable)

    UNKNOWN is the safe default. Missing claims_map, missing evidence blobs,
    or missing oracle_class metadata all produce UNKNOWN — not clean.
    """

    run_id: str
    status: str  # "clean" | "tainted" | "unknown"
    publish_min_class: int
    reasons: list[TaintReason] = field(default_factory=list)
    unknown_reasons: list[str] = field(default_factory=list)
    total_high_confidence_claims: int = 0
    oracle_backed_claims: int = 0
    clean_claims: int = 0

    @property
    def tainted(self) -> bool:
        return self.status == "tainted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "publish_min_class": self.publish_min_class,
            "reasons": [r.to_dict() for r in self.reasons],
            "unknown_reasons": self.unknown_reasons,
            "total_high_confidence_claims": self.total_high_confidence_claims,
            "oracle_backed_claims": self.oracle_backed_claims,
            "clean_claims": self.clean_claims,
        }


class PublishThreshold:
    """Scope-aware publish threshold.

    v0: single threshold for all scopes.
    Future: per-scope thresholds (e.g., auth files need class 2).
    """

    def __init__(self, default: int = 1, scopes: dict[str, int] | None = None):
        self._default = default
        self._scopes = scopes or {}

    def min_class(self, scope: str | None = None) -> int:
        if scope is not None and scope in self._scopes:
            return self._scopes[scope]
        return self._default

    @property
    def default(self) -> int:
        return self._default


def _build_blob_class_map(store: Any, run_id: str) -> dict[str, int]:
    """Build blob ref -> oracle_class map from EVIDENCE_PUT events.

    Inlined from receipt_kernel.invariants._helpers.build_blob_class_map
    to avoid importing private modules. Same ~10-line scan.
    """
    events = store.get_events(run_id, event_type="EVIDENCE_PUT")
    result: dict[str, int] = {}
    for ev in events:
        payload = ev.get("payload") or {}
        evidence = payload.get("evidence") or {}
        ref = evidence.get("ref")
        meta = payload.get("meta") or {}
        oracle_class = meta.get("oracle_class")
        if isinstance(ref, str) and isinstance(oracle_class, int):
            result[ref] = oracle_class
    return result


def _load_claims_map(store: Any, run_id: str) -> dict[str, Any] | None:
    """Load and parse the claims_map evidence blob.

    Inlined from receipt_kernel.invariants._helpers.load_evidence_json
    to avoid importing private modules.
    """
    events = store.get_events(run_id, event_type="EVIDENCE_PUT")
    sha = None
    for ev in reversed(events):
        payload = ev.get("payload") or {}
        if payload.get("key") == "claims_map":
            evidence = payload.get("evidence") or {}
            sha = evidence.get("sha256")
            break

    if sha is None:
        return None

    raw = store.get_blob(sha)
    if raw is None:
        return None

    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def compute_taint(
    store: Any,
    run_id: str,
    threshold: PublishThreshold | None = None,
) -> RunTaint:
    """Compute release taint for a kernel run.

    Uses only the store's public API (get_events, get_blob).
    No receipt_kernel.invariants._helpers import.

    Args:
        store: SqliteReceiptStore (or compatible)
        run_id: Kernel run ID
        threshold: Publish threshold (default: class 1 for all scopes)

    Returns:
        RunTaint with status, reasons, and counts.
    """
    threshold = threshold or PublishThreshold()
    publish_min = threshold.default

    # Load claims_map
    claims_doc = _load_claims_map(store, run_id)
    if claims_doc is None:
        return RunTaint(
            run_id=run_id,
            status="unknown",
            publish_min_class=publish_min,
            unknown_reasons=["claims_map evidence blob missing or unreadable"],
        )

    claims = claims_doc.get("claims") or []

    # Filter to high-confidence claims only (HARD claims that "matter")
    high_claims = [
        c for c in claims
        if isinstance(c, dict) and str(c.get("confidence", "")).lower() == "high"
    ]

    if not high_claims:
        return RunTaint(
            run_id=run_id,
            status="clean",
            publish_min_class=publish_min,
            total_high_confidence_claims=0,
            oracle_backed_claims=0,
            clean_claims=0,
        )

    # Build blob ref -> oracle_class map
    blob_class_map = _build_blob_class_map(store, run_id)

    reasons: list[TaintReason] = []
    unknown_reasons: list[str] = []
    oracle_backed = 0
    clean = 0

    for i, c in enumerate(high_claims):
        cid = c.get("id", f"idx:{i}")
        scope = c.get("scope")  # plumbed, not populated
        evrefs = c.get("evidence_refs") or []

        # Find oracle evidence among this claim's refs
        oracle_refs = [
            ref for ref in evrefs
            if isinstance(ref, str) and ref in blob_class_map
        ]

        if not oracle_refs:
            # No oracle evidence — not our concern for taint
            # (confidence.sanity checks that HARD claims have oracle evidence)
            continue

        oracle_backed += 1
        min_required = threshold.min_class(scope)

        # Check for refs cited but missing oracle_class data
        missing_class_refs = [
            ref for ref in evrefs
            if isinstance(ref, str) and ref not in blob_class_map
            and ref in _collect_all_blob_refs(store, run_id)
        ]
        if missing_class_refs:
            unknown_reasons.append(
                f"claim {cid}: oracle evidence missing class metadata"
            )
            continue

        # Max class over all cited oracles (documented simplification)
        max_class = max(blob_class_map[ref] for ref in oracle_refs)

        if max_class < min_required:
            reasons.append(TaintReason(
                claim_id=cid,
                observed_class=max_class,
                publish_min_class=min_required,
            ))
        else:
            clean += 1

    # Derive status
    if unknown_reasons:
        status = "unknown"
    elif reasons:
        status = "tainted"
    else:
        status = "clean"

    return RunTaint(
        run_id=run_id,
        status=status,
        publish_min_class=publish_min,
        reasons=reasons,
        unknown_reasons=unknown_reasons,
        total_high_confidence_claims=len(high_claims),
        oracle_backed_claims=oracle_backed,
        clean_claims=clean,
    )


def _collect_all_blob_refs(store: Any, run_id: str) -> set[str]:
    """Collect all blob refs from EVIDENCE_PUT events."""
    events = store.get_events(run_id, event_type="EVIDENCE_PUT")
    refs: set[str] = set()
    for ev in events:
        evidence = (ev.get("payload") or {}).get("evidence") or {}
        ref = evidence.get("ref")
        if isinstance(ref, str):
            refs.add(ref)
    return refs
