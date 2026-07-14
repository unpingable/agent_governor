# SPDX-License-Identifier: Apache-2.0
"""Approval-binds-plan_ref verification — seam ruling B (2026-07-14).

An approval witness authorizes exactly ONE plan identity because its attested
content names that plan's exact byte hash. AG establishes authority-critical
identity by **re-hashing the exact evidence bytes presented in the adjudication
request**; the caller-supplied ``source_plan_digest`` is a CONSISTENCY
ASSERTION, never the authority basis. References/digests may locate or
cross-check evidence — they never substitute for independent verification.

Rejected alternatives (do not reintroduce): trusting maude's upstream verdict
(option A — AG would accept a conclusion about an authority predicate instead of
adjudicating it); verifying a content-addressed *reference* instead of the bytes
(option B′ — trust relocation onto an unruled retrieval substrate). B verifies
bytes AG holds. See ``docs/campaigns/nightshift-functional-mvp/design-approval-binds-plan-ref.md``.

NOT a witness *authenticity* check: ``sha256(witness_bytes) == digest`` is
**integrity** (bytes match their self-digest). Witness AUTHENTICITY — that the
digest corresponds to a recorded operator approval — is established UPSTREAM at
minting, not here (out of scope; see the spec non-goals). A forged-but-
self-consistent witness is an operator-tooling concern, not this gate's.
"""

from __future__ import annotations

import hashlib
import json

#: Known approval-witness content versions (closed set; unknown → refuse).
APPROVAL_WITNESS_VERSIONS = frozenset({"approval-witness/v1"})
#: The only ``decision`` value that authorizes execution (closed).
AUTHORIZING_DECISION = "approve"
#: Size bounds — "plans, not Blu-rays."
MAX_PLAN_BYTES = 1 << 20      # 1 MiB
MAX_WITNESS_BYTES = 1 << 16   # 64 KiB

_SHA256_PREFIX = "sha256:"

#: Closed refusal vocabulary (2 kinds).
REFUSAL_PLAN_REF_MISMATCH = "approval_plan_ref_mismatch"
REFUSAL_WITNESS_INVALID = "approval_witness_invalid"


class ApprovalBindingError(ValueError):
    """The approval witness does not bind the exact plan bytes. Fail-closed:
    no grant is minted. Carries a closed-vocabulary ``refusal_kind``."""

    def __init__(self, refusal_kind: str, message: str) -> None:
        super().__init__(message)
        self.refusal_kind = refusal_kind


def _snapshot(x: bytes | bytearray | memoryview | str | None) -> bytes | None:
    """Snapshot to IMMUTABLE bytes immediately — a digest-verified *mutable*
    buffer is not a frozen witness (S7 mutable-verified-buffer scar). ``bytes(x)``
    copies a bytearray/memoryview; a str is UTF-8 encoded (the exact bytes the
    producer hashed). A non-bytes-like input (dict/list/int/…) is not evidence
    bytes — raise ``TypeError`` so the caller refuses within the closed
    vocabulary rather than letting ``bytes(x)`` escape as a raw error."""
    if x is None:
        return None
    if isinstance(x, str):
        return x.encode("utf-8")
    if isinstance(x, (bytes, bytearray, memoryview)):
        return bytes(x)
    raise TypeError(f"expected bytes or str, got {type(x).__name__}")


def _sha256_ref(data: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(data).hexdigest()


def _normalize_digest(d: object) -> str:
    """Normalize ``sha256:<hex>`` or bare 64-hex to the prefixed lowercase form
    so all three digests compare in one shape. Anything not a well-formed sha256
    digest → ``""`` (the caller treats that as mismatch/invalid, fail-closed)."""
    if not isinstance(d, str):
        return ""
    s = d.strip().lower()
    if s.startswith(_SHA256_PREFIX):
        s = s[len(_SHA256_PREFIX):]
    if len(s) == 64 and all(c in "0123456789abcdef" for c in s):
        return _SHA256_PREFIX + s
    return ""


def verify_approval_binds_plan(
    *,
    plan_bytes: bytes | bytearray | memoryview | str | None,
    witness_bytes: bytes | bytearray | memoryview | str | None,
    source_plan_digest: str,
    approval_witness_digest: str,
) -> str:
    """Verify that the approval witness binds *these exact plan bytes* (seam B).

    Returns the AG-computed ``actual_plan_ref`` on success; raises
    ``ApprovalBindingError`` (fail-closed, no grant) otherwise. Both byte blobs
    are snapshotted to immutable ``bytes`` at entry and read exactly once
    (TOCTOU closed).

    The load-bearing invariant:
        source_plan_digest == sha256(plan_bytes) == witness.plan_ref
    all three identical, where ``sha256(plan_bytes)`` is computed by AG here.
    The caller digest is only a consistency assertion — replay refuses even if
    the caller lies about ``source_plan_digest``.
    """
    try:
        pb = _snapshot(plan_bytes)
        wb = _snapshot(witness_bytes)
    except TypeError as exc:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID, f"evidence bytes malformed: {exc}"
        ) from exc

    # --- mandatory bytes, fail-closed (#5) ---
    if not pb:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID, "plan_bytes absent/empty — refused (fail-closed)"
        )
    if not wb:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID, "witness_bytes absent/empty — refused (fail-closed)"
        )
    # --- size bounds (pin 8) ---
    if len(pb) > MAX_PLAN_BYTES:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID, f"plan_bytes exceeds {MAX_PLAN_BYTES} bytes — refused"
        )
    if len(wb) > MAX_WITNESS_BYTES:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID, f"witness_bytes exceeds {MAX_WITNESS_BYTES} bytes — refused"
        )

    # --- witness INTEGRITY (not authenticity): bytes match their self-digest ---
    claimed_wd = _normalize_digest(approval_witness_digest)
    actual_wd = _sha256_ref(wb)
    if not claimed_wd or claimed_wd != actual_wd:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID,
            f"approval_witness_digest does not match witness bytes "
            f"(claimed {approval_witness_digest!r}, actual {actual_wd})",
        )

    # --- parse witness content from the EXACT bytes (never re-serialized) (#1) ---
    try:
        witness = json.loads(wb.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID, f"witness is not UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(witness, dict):
        raise ApprovalBindingError(REFUSAL_WITNESS_INVALID, "witness must be a JSON object")
    ver = witness.get("witness_version")
    decision = witness.get("decision")
    w_plan_ref = witness.get("plan_ref")
    if not (isinstance(ver, str) and isinstance(decision, str) and isinstance(w_plan_ref, str)):
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID,
            "witness must carry string witness_version, decision, and plan_ref",
        )
    # --- known version (#6) ---
    if ver not in APPROVAL_WITNESS_VERSIONS:
        raise ApprovalBindingError(REFUSAL_WITNESS_INVALID, f"unknown witness_version {ver!r}")
    # --- decision authorizes (#2, closed vocabulary) ---
    if decision != AUTHORIZING_DECISION:
        raise ApprovalBindingError(
            REFUSAL_WITNESS_INVALID,
            f"witness decision {decision!r} does not authorize execution",
        )

    # --- AG computes plan identity from the EXACT bytes it was given ---
    actual_plan_ref = _sha256_ref(pb)
    src = _normalize_digest(source_plan_digest)
    wpr = _normalize_digest(w_plan_ref)
    # --- the triple must be all-identical (the replay defense) ---
    if not (src and wpr and src == actual_plan_ref == wpr):
        raise ApprovalBindingError(
            REFUSAL_PLAN_REF_MISMATCH,
            "approval witness does not bind these plan bytes "
            f"(source_plan_digest={source_plan_digest!r}, "
            f"sha256(plan_bytes)={actual_plan_ref}, witness.plan_ref={w_plan_ref!r})",
        )
    return actual_plan_ref


__all__ = [
    "verify_approval_binds_plan",
    "ApprovalBindingError",
    "APPROVAL_WITNESS_VERSIONS",
    "AUTHORIZING_DECISION",
    "MAX_PLAN_BYTES",
    "MAX_WITNESS_BYTES",
    "REFUSAL_PLAN_REF_MISMATCH",
    "REFUSAL_WITNESS_INVALID",
]
