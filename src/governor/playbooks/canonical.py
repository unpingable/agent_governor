# SPDX-License-Identifier: Apache-2.0
"""Deterministic canonical form for a ``PlaybookSpec`` (Slice 0).

The format people edit is not the thing custody trusts. A ``PlaybookSpec`` (the
typed result of parsing the restricted YAML) is projected to a canonical mapping
and serialized with the repo's canonical JSON (sorted keys, compact separators,
ASCII-safe) — so formatting noise and mapping key-order in the source do not
change the bytes. Step **order** is preserved (it is semantic; reordering steps
is a different procedure).
"""

from __future__ import annotations

from typing import Any

from governor.gate_receipt import canonical_json

from .spec import PlaybookSpec

# Bump when the canonical projection changes shape (feeds the digest basis).
CANONICAL_VERSION = "playbook-canonical.v0"


def canonical_spec_mapping(spec: PlaybookSpec) -> dict[str, Any]:
    """The canonical mapping projection of a spec (pre-serialization).

    ``imports`` (Slice 2) appears ONLY when non-empty — an import-less spec
    canonicalizes byte-identically to its Slice 0 form, so its
    ``playbook_spec_digest`` is unchanged (no canonical/digest version bump). The
    import REFS are authored content and belong in this spec's digest ("I
    reference X"); the *resolved* dependency content does NOT — that is the
    separate ``dependency_closure_digest`` (no free smoothie).
    """
    mapping: dict[str, Any] = {
        "schema": spec.schema,
        "kind": spec.kind,
        "name": spec.name,
        "steps": [
            {"id": s.id, "action": s.action, "target": s.target} for s in spec.steps
        ],
    }
    if spec.imports:
        # Imports are a dependency SET — declaration order is not semantic (unlike
        # steps, which are an ordered sequence). Sorting makes the root spec digest
        # (and therefore the closure digest) stable under import reordering, while a
        # change to WHICH refs are present still moves the digest.
        mapping["imports"] = sorted(spec.imports)
    return mapping


def canonical_spec_bytes(spec: PlaybookSpec) -> bytes:
    """Deterministic canonical bytes for a spec. Stable under source formatting /
    mapping key-order noise; sensitive to any semantic change (including step
    order)."""
    return canonical_json(canonical_spec_mapping(spec))
