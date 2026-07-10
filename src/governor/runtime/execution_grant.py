# SPDX-License-Identifier: Apache-2.0
"""Execution-grant activation (approval-compression, S2a).

The issuance half of the seam: a plan **requests** execution scope, activation
**mints** a first-class grant. RATIFIED boundary (2026-07-10): the grant is a
first-class artifact minted here, NOT an ``execution_grant:`` plan block — a
plan may only request; only activation may grant.

    approved plan → (deterministic projection) → ExecutionRequest
                  → activate_execution_grant() → ExecutionGrantArtifact
                  → (S1) repeated checked uses

Activation is **deterministic + idempotent**: the ``grant_id`` is derived from
the content digest, so re-activating the same (plan, witness, effects) yields
the same grant — no clock, no random, no double-mint. v1 **locks the dangerous
axes** (network/git/secrets/privilege denied — ``enforcement:
declared-effects-only``); a request for them is recorded in ``unmet_axes`` for
transparency but never granted (nothing armed — MVP line).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from governor.gate_receipt import canonical_json
from governor.runtime.grant_use_gate import CommandGrant, ExecutionGrant

DERIVATION_VERSION = "execution-grant/v1"
ENFORCEMENT_DECLARED_ONLY = "declared-effects-only"

#: horizons a v1 grant may declare.
VALID_HORIZONS = frozenset({"run", "session"})


@dataclass(frozen=True)
class ExecutionRequest:
    """What an approved plan ASKS for — carries no authority. Deterministically
    projected from the plan by the operator surface (``scope_allowlist`` →
    write_paths, declared command surface → commands); the daemon mints from
    it. ``source_plan_digest`` and ``approval_witness_digest`` bind the mint to
    the specific approved plan and the operator's witnessed approval."""

    write_paths: frozenset[str]
    commands: tuple[CommandGrant, ...]
    source_plan_digest: str
    approval_witness_digest: str
    horizon: str = "run"
    network_requested: bool = False
    git_requested: bool = False


@dataclass(frozen=True)
class ExecutionGrantArtifact:
    """A minted, first-class execution grant. ``grant`` is the pure effect
    surface S1 checks; the surrounding fields are the artifact's identity and
    provenance (what the activation receipt records)."""

    grant_id: str            # "sgr_<12hex>", content-derived (idempotent)
    grant_digest: str        # "sha256:<64hex>" over the canonical body
    source_plan_digest: str
    approval_witness_digest: str
    derivation_version: str
    horizon: str
    enforcement: str         # ENFORCEMENT_DECLARED_ONLY
    grant: ExecutionGrant
    unmet_axes: tuple[str, ...] = field(default_factory=tuple)

    def receipt_body(self) -> dict:
        """The activation-receipt body (S3 emits this as a gate receipt)."""
        return {
            "grant_id": self.grant_id,
            "grant_digest": self.grant_digest,
            "source_plan_digest": self.source_plan_digest,
            "approval_witness_digest": self.approval_witness_digest,
            "derivation_version": self.derivation_version,
            "horizon": self.horizon,
            "enforcement": self.enforcement,
            "write_paths": sorted(self.grant.write_paths),
            "commands": _commands_json(self.grant.commands),
            "network": "denied",
            "git": "denied",
            "secrets": "denied",
            "privilege": "denied",
            "unmet_axes": list(self.unmet_axes),
        }


class ActivationError(ValueError):
    """The request cannot be minted into a grant (malformed / unknown horizon).
    Fail-closed: no grant is produced."""


def _commands_json(commands: tuple[CommandGrant, ...]) -> list[dict]:
    return [
        {"program": c.program, "argv_prefix": list(c.argv_prefix)}
        for c in sorted(commands, key=lambda c: (c.program, c.argv_prefix))
    ]


def _canonical_body(
    write_paths: frozenset[str],
    commands: tuple[CommandGrant, ...],
    source_plan_digest: str,
    approval_witness_digest: str,
    horizon: str,
) -> dict:
    # Deterministic, order-independent: sets sorted, commands sorted. The body
    # excludes grant_id (which derives FROM this body's digest).
    return {
        "derivation_version": DERIVATION_VERSION,
        "source_plan_digest": source_plan_digest,
        "approval_witness_digest": approval_witness_digest,
        "horizon": horizon,
        "enforcement": ENFORCEMENT_DECLARED_ONLY,
        "write_paths": sorted(write_paths),
        "commands": _commands_json(commands),
        "network": "denied",
        "git": "denied",
        "secrets": "denied",
        "privilege": "denied",
    }


def activate_execution_grant(request: ExecutionRequest) -> ExecutionGrantArtifact:
    """Mint a first-class ``ExecutionGrantArtifact`` from a request. PURE +
    deterministic + idempotent. Fail-closed on a malformed request.

    v1 grants only ``write_paths`` + ``commands``; network/git/secrets/privilege
    are locked (``enforcement: declared-effects-only``). A request for a locked
    axis is recorded in ``unmet_axes`` — visible, never silently honored."""
    if not request.source_plan_digest or not request.approval_witness_digest:
        raise ActivationError(
            "activation requires both source_plan_digest and approval_witness_digest "
            "(a grant is bound to a specific approved plan + witnessed approval)"
        )
    if request.horizon not in VALID_HORIZONS:
        raise ActivationError(
            f"unknown horizon {request.horizon!r}; expected one of {sorted(VALID_HORIZONS)}"
        )

    grant = ExecutionGrant(
        write_paths=frozenset(request.write_paths),
        commands=tuple(sorted(request.commands, key=lambda c: (c.program, c.argv_prefix))),
        network_allowed=False,  # v1: locked, always. Nothing armed.
        git_allowed=False,
    )
    body = _canonical_body(
        grant.write_paths, grant.commands,
        request.source_plan_digest, request.approval_witness_digest, request.horizon,
    )
    digest_hex = hashlib.sha256(canonical_json(body)).hexdigest()
    unmet = tuple(
        axis for axis, requested in
        (("network", request.network_requested), ("git", request.git_requested))
        if requested
    )
    return ExecutionGrantArtifact(
        grant_id=f"sgr_{digest_hex[:12]}",
        grant_digest=f"sha256:{digest_hex}",
        source_plan_digest=request.source_plan_digest,
        approval_witness_digest=request.approval_witness_digest,
        derivation_version=DERIVATION_VERSION,
        horizon=request.horizon,
        enforcement=ENFORCEMENT_DECLARED_ONLY,
        grant=grant,
        unmet_axes=unmet,
    )


__all__ = [
    "ExecutionRequest", "ExecutionGrantArtifact", "ActivationError",
    "activate_execution_grant",
    "DERIVATION_VERSION", "ENFORCEMENT_DECLARED_ONLY", "VALID_HORIZONS",
]
