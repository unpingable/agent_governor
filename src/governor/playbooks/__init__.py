# SPDX-License-Identifier: Apache-2.0
"""Governed Playbooks — the inert authoring + measurement layer.

Slice 0 (custody over authored bytes): restricted-YAML source → deterministic
canonical ``PlaybookSpec`` bytes → ``playbook_spec_digest``. **Measurement only.**
No Wicket, no Standing, no LA, no certified_kind, no dependency closure, no
ConvergenceFence — those are AG / sibling-organ surfaces this layer *cites*, never
redefines (see ``docs/playbooks/``). This package mints exactly one thing: a stable
digest over the authored bytes.
"""

from __future__ import annotations

from .canonical import (
    CANONICAL_VERSION,
    canonical_spec_bytes,
    canonical_spec_mapping,
)
from .certify import (
    CERT_MEASUREMENT_BASIS_VERSION,
    CHECKER_VERSION,
    KIND_PROCEDURE,
    KNOWN_KINDS,
    CertificationError,
    CertifiedKindMeasurement,
    KindCheckError,
    UnsupportedKindError,
    certified_kind_measurement_digest,
    certify,
    measurement_basis,
)
from .closure import (
    CLOSURE_DIGEST_BASIS_VERSION,
    ClosureError,
    DependencyClosure,
    ImportCycleError,
    ImportNotFoundError,
    Resolver,
    closure_basis,
    dependency_closure_digest,
    resolve_closure,
    resolve_closure_digest,
)
from .digest import DIGEST_BASIS_VERSION, digest_basis, playbook_spec_digest
from .spec import (
    PARSER_VERSION,
    SCHEMA_V0,
    PlaybookError,
    PlaybookSchemaError,
    PlaybookSpec,
    PlaybookStep,
    RestrictedYAMLError,
    parse_playbook,
)

__all__ = [
    "PARSER_VERSION",
    "SCHEMA_V0",
    "PlaybookError",
    "PlaybookSchemaError",
    "PlaybookSpec",
    "PlaybookStep",
    "RestrictedYAMLError",
    "parse_playbook",
    "CANONICAL_VERSION",
    "canonical_spec_bytes",
    "canonical_spec_mapping",
    "DIGEST_BASIS_VERSION",
    "digest_basis",
    "playbook_spec_digest",
    "CHECKER_VERSION",
    "CERT_MEASUREMENT_BASIS_VERSION",
    "KIND_PROCEDURE",
    "KNOWN_KINDS",
    "CertificationError",
    "CertifiedKindMeasurement",
    "KindCheckError",
    "UnsupportedKindError",
    "certify",
    "measurement_basis",
    "certified_kind_measurement_digest",
    "CLOSURE_DIGEST_BASIS_VERSION",
    "Resolver",
    "ClosureError",
    "DependencyClosure",
    "ImportCycleError",
    "ImportNotFoundError",
    "closure_basis",
    "dependency_closure_digest",
    "resolve_closure",
    "resolve_closure_digest",
]
