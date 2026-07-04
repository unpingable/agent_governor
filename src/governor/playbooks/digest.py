# SPDX-License-Identifier: Apache-2.0
"""``playbook_spec_digest`` — custody over the authored bytes (Slice 0).

The digest is SHA-256 over a canonical-JSON **basis** that includes the
canonical spec AND explicit version tags (digest / parser / canonical). Binding
the versions into the digest means a change to *how* bytes are canonicalized or
parsed yields a different digest — the digest never silently means two things.
This is a measurement, not authority: it answers "which authored bytes were
certified", nothing more.
"""

from __future__ import annotations

from typing import Any

from governor.gate_receipt import canonical_json, content_hash

from .canonical import CANONICAL_VERSION, canonical_spec_mapping
from .spec import PARSER_VERSION, PlaybookSpec

# Bump if the basis composition (which versions/fields are bound) changes.
DIGEST_BASIS_VERSION = "playbook-digest.v0"


def digest_basis(spec: PlaybookSpec) -> dict[str, Any]:
    """The exact object the digest is taken over — versions + canonical spec.

    Exposed (not just hashed) so the version-binding is testable and a reviewer
    can see precisely what the digest commits to.
    """
    return {
        "digest_basis": DIGEST_BASIS_VERSION,
        "parser_version": PARSER_VERSION,
        "canonical_version": CANONICAL_VERSION,
        "spec": canonical_spec_mapping(spec),
    }


def playbook_spec_digest(spec: PlaybookSpec) -> str:
    """SHA-256 hex digest over the version-bound canonical basis of ``spec``."""
    return content_hash(canonical_json(digest_basis(spec)))
