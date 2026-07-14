# SPDX-License-Identifier: Apache-2.0
"""Approval-witness producer — the operator-minting half of seam B.

The approval slice (`approval_binding.py`) defined the witness *format* AG
enforces but nothing *produced* one. This mints a witness that BINDS a specific
plan's exact bytes: `plan_ref = sha256(plan_bytes)`, formatted as the UTF-8 JSON
AG's ``verify_approval_binds_plan`` accepts. The invariant that ties the two
halves together — and the test that proves it — is a ROUND-TRIP: a witness the
producer mints for plan P verifies for P and refuses beside any other plan.

The producer **cannot forge a cross-plan binding**: `plan_ref` is the hash of
the exact bytes it is given, so a minted witness only ever binds those bytes.

Scope fence (matches the approval slice non-goals):
- This does NOT establish witness *authenticity*. Running the producer IS the
  operator's approval act; a governed signing/attestation layer (that a witness
  reflects a *recorded, authorized* operator decision) is future work in
  standing/testimony territory, NOT here.
- ``decision`` is explicit and required at the API — there is no silent
  auto-approve default in the minting function.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from governor.runtime.approval_binding import (
    APPROVAL_WITNESS_VERSIONS,
    AUTHORIZING_DECISION,
)

#: The witness version this producer emits. Guarded against drifting out of the
#: verifier's known set.
WITNESS_VERSION = "approval-witness/v1"
assert WITNESS_VERSION in APPROVAL_WITNESS_VERSIONS, "producer version not accepted by the verifier"

_SHA256_PREFIX = "sha256:"

#: MUST match ``maude/plan/witness.py`` ``sanitize_ref`` — the file-witness
#: resolver keys a non-digest ``approval_ref`` to ``<witness_dir>/<sanitized>``.
#: A drift here only affects FINDABILITY (fail-closed: witness not found → the
#: governed plan refuses), never the authority binding, which is content-addressed.
_SANITIZE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_ref(ref: str) -> str:
    """A ref's on-disk witness filename (mirrors maude's resolver convention)."""
    return _SANITIZE.sub("_", ref)


def _sha256_ref(data: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(data).hexdigest()


def _plan_bytes(plan: bytes | bytearray | memoryview | str) -> bytes:
    # maude hashes the true file bytes (runner.py: read_bytes().decode utf-8),
    # so plan_ref over sha256(bytes) is the same content-address both sides
    # compute. A str is UTF-8 encoded to the same bytes.
    if isinstance(plan, str):
        return plan.encode("utf-8")
    return bytes(plan)


@dataclass(frozen=True)
class ApprovalWitness:
    """A minted approval witness. ``witness_bytes`` are what land in the witness
    directory and what AG re-hashes; ``approval_witness_digest`` is over exactly
    those bytes; ``plan_ref`` is the plan identity it binds."""

    witness_bytes: bytes
    approval_witness_digest: str
    plan_ref: str
    decision: str


def build_approval_witness(
    plan: bytes | bytearray | memoryview | str,
    decision: str,
) -> ApprovalWitness:
    """Mint a witness binding ``plan``'s exact bytes. ``decision`` is explicit
    (``"approve"`` authorizes; anything else the verifier will refuse — e.g. a
    recorded ``"deny"``). Serialization is canonical (sorted keys, tight
    separators) so a given (plan, decision) always yields identical bytes."""
    pb = _plan_bytes(plan)
    if not pb:
        raise ValueError("plan bytes are required to mint an approval witness")
    if not isinstance(decision, str) or not decision:
        raise ValueError("decision must be a non-empty string (e.g. 'approve')")
    plan_ref = _sha256_ref(pb)
    obj = {"witness_version": WITNESS_VERSION, "decision": decision, "plan_ref": plan_ref}
    witness_bytes = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ApprovalWitness(
        witness_bytes=witness_bytes,
        approval_witness_digest=_sha256_ref(witness_bytes),
        plan_ref=plan_ref,
        decision=decision,
    )


def write_approval_witness(
    witness_dir: str | Path,
    approval_ref: str,
    plan: bytes | bytearray | memoryview | str,
    decision: str,
) -> Path:
    """Mint and write the witness to the directory maude's resolver reads,
    keyed by ``approval_ref``. Returns the written path. Refuses to overwrite an
    existing witness at that ref (approval is not silently re-minted)."""
    root = Path(witness_dir)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / sanitize_ref(approval_ref)
    if dest.exists():
        raise FileExistsError(
            f"a witness already exists at {dest} — refusing to overwrite an "
            "approval act (remove it explicitly to re-mint)"
        )
    witness = build_approval_witness(plan, decision)
    dest.write_bytes(witness.witness_bytes)
    return dest


__all__ = [
    "WITNESS_VERSION",
    "ApprovalWitness",
    "build_approval_witness",
    "write_approval_witness",
    "sanitize_ref",
]
