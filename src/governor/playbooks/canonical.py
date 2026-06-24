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
    """The canonical mapping projection of a spec (pre-serialization)."""
    return {
        "schema": spec.schema,
        "kind": spec.kind,
        "name": spec.name,
        "steps": [
            {"id": s.id, "action": s.action, "target": s.target} for s in spec.steps
        ],
    }


def canonical_spec_bytes(spec: PlaybookSpec) -> bytes:
    """Deterministic canonical bytes for a spec. Stable under source formatting /
    mapping key-order noise; sensitive to any semantic change (including step
    order)."""
    return canonical_json(canonical_spec_mapping(spec))
