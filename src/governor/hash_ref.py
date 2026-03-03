# SPDX-License-Identifier: Apache-2.0
"""
HashRef — parse and compare content-addressed hashes across modules.

Problem: gate_receipt.content_hash() returns raw hex ("9f86d08...") while
signals/envelope.content_hash() and receipt_kernel return "sha256:9f86d08...".
These are the same digest but string comparison fails.

Solution: a small value type that parses both formats and compares by
(algorithm, digest) regardless of prefix.  Does NOT rewrite stored hashes —
it normalizes at the comparison boundary.

Non-canonical dedup fingerprints (session_continuity, scalar_collapse, etc.)
are a different regime and should NOT use HashRef.  Those are renamed to
dedup_fingerprint() to prevent accidental promotion into content-addressing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches "sha256:<hex>" or "sha384:<hex>" etc.
_PREFIXED_RE = re.compile(r"^([a-z0-9]+):([0-9a-f]+)$")


@dataclass(frozen=True, slots=True)
class HashRef:
    """Parsed content-addressed hash reference.

    Attributes:
        alg: Hash algorithm (e.g., "sha256").
        digest: Lowercase hex digest.
        prefixed: Whether the original string had an algorithm prefix.
    """

    alg: str
    digest: str
    prefixed: bool

    @classmethod
    def parse(cls, raw: str, *, default_alg: str = "sha256") -> HashRef:
        """Parse a hash string in either format.

        Accepts:
          - "sha256:9f86d08..." (prefixed)
          - "9f86d08..."       (raw hex, assumes default_alg)

        Raises ValueError for empty strings or non-hex digests.
        """
        if not raw:
            raise ValueError("Empty hash string")

        raw = raw.strip()
        m = _PREFIXED_RE.match(raw)
        if m:
            return cls(alg=m.group(1), digest=m.group(2), prefixed=True)

        # Raw hex — validate it's actually hex
        lowered = raw.lower()
        if not all(c in "0123456789abcdef" for c in lowered):
            raise ValueError(f"Not a valid hex digest: {raw!r}")

        return cls(alg=default_alg, digest=lowered, prefixed=False)

    def canonical(self) -> str:
        """Return the prefixed form: 'alg:digest'."""
        return f"{self.alg}:{self.digest}"

    def hex(self) -> str:
        """Return the raw hex digest without prefix."""
        return self.digest

    def matches(self, other: HashRef) -> bool:
        """Compare two HashRefs by (alg, digest), ignoring prefix format."""
        return self.alg == other.alg and self.digest == other.digest

    def __eq__(self, other: object) -> bool:
        if isinstance(other, HashRef):
            return self.alg == other.alg and self.digest == other.digest
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.alg, self.digest))

    def __str__(self) -> str:
        return self.canonical()

    def __repr__(self) -> str:
        return f"HashRef({self.canonical()!r})"
