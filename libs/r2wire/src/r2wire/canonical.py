# SPDX-License-Identifier: Apache-2.0
"""Canonical JSON serialization and hashing.

MUST produce byte-identical output to receipt_kernel.envelope.canonical_json
for the same input.  If these ever diverge, the two audit trails become
incompatible.  See tests/test_canonical_vectors.py for the tripwire.

Rules:
  - Sorted keys
  - Compact separators (",", ":")
  - ensure_ascii=True (no raw Unicode in output)
  - allow_nan=False (no floats that aren't real numbers)
  - UTF-8 encoded bytes
  - NFC normalization of input strings before serialization
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


def _nfc_normalize(obj: Any) -> Any:
    """Recursively NFC-normalize all strings in a JSON-like object."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {_nfc_normalize(k): _nfc_normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_nfc_normalize(item) for item in obj]
    return obj


def canonical_json_bytes(obj: Any, *, nfc: bool = True) -> bytes:
    """Deterministic JSON serialization for hashing.

    When nfc=True (default), all strings are NFC-normalized before
    serialization.  Set nfc=False for receipt_kernel compatibility
    (which does not NFC-normalize).

    Do not change the json.dumps parameters without bumping the
    protocol version.
    """
    target = _nfc_normalize(obj) if nfc else obj
    return json.dumps(
        target,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def hash_bytes(data: bytes) -> str:
    """SHA-256 hex digest with 'sha256:' prefix."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def hash_json(obj: Any, *, nfc: bool = True) -> str:
    """Canonical JSON → SHA-256 hash."""
    return hash_bytes(canonical_json_bytes(obj, nfc=nfc))
