# SPDX-License-Identifier: Apache-2.0
"""Provider registry — Slice 2 of the provider/agent integration contract.

DRAFT / CANDIDATE substrate. **Descriptors only.** No provider is declared
runtime-conformant here; no live dispatch is wired (Slice 4, gated on CD-4); no
Maude/Claude-Code descriptors are registered (Slice 3). See
``docs/api/provider-integration.md`` and ``schemas/provider_descriptor.v1.json``.

This module resolves the three things the contract review (provider-integration
§6) said MUST be specified before this slice ships:

1. **How conformance is proven.** A :class:`ProviderDescriptor` is a
   *declaration* — a claim, not a grant (NLAI: language is a proposal, not an
   authority). Registering one files the claim; it never makes the provider
   trusted or its output admissible. From a descriptor alone we can check only
   **STRUCTURAL** conformance (valid kind, known capability vocabulary, and —
   fail-closed — zero authority claims). **RUNTIME** conformance (speaks the
   shapes / reports lifecycle not verdicts / only further restricts / obstruction
   honesty) needs live evidence and is out of scope until a provider actually
   runs (Slice 3+). :class:`ConformanceLevel` tops out at ``STRUCTURAL`` here and
   can only advance on evidence, never on assertion.

2. **How it is revoked / expires.** :meth:`ProviderRegistry.revoke` drops a
   provider from routing eligibility (the entry stays for audit). Freshness is by
   descriptor ``version``: a version change is a NEW descriptor that must be
   re-registered (re-probed); a stale descriptor cannot silently persist because
   :meth:`register` replaces by ``provider_id``.

3. **What a registry entry does.** Routing **eligibility only — never trust.**
   The registry is a phone book, not a court: it answers "which known providers
   *declare* they can perform this capability set?" It has NO method that admits,
   authorizes, trusts, or grants. AG dispatch (``governed_dispatch``) remains the
   sole decider; a lookup result is a candidate list, explicitly not a permission.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from governor.chain_gate import CapabilityClass
from governor.gate_receipt import canonical_json, content_hash

#: Capability-shaped provider kinds (mirrors provider_descriptor.v1.json).
PROVIDER_KINDS = frozenset(
    {
        "execution_harness",
        "agent_runtime",
        "transform_provider",
        "substrate_courier",
        "external_witness",
        "communication_adapter",
        "artifact_store",
    }
)

#: The capability vocabulary is reused verbatim from chain_gate — not a new enum.
_CAPABILITY_VALUES = frozenset(c.value for c in CapabilityClass)


class ConformanceLevel(str, Enum):
    """How far a descriptor has been checked. Advances only on evidence."""

    UNVERIFIED = "unverified"  # declared, not yet checked
    STRUCTURAL = "structural"  # descriptor passes structural checks — this slice's ceiling
    # RUNTIME conformance is intentionally absent: it requires live runs (Slice 3+).


class DescriptorRejected(ValueError):
    """Fail-closed: a descriptor that violates a structural conformance rule is
    rejected at registration, never stored as trusted-but-invalid."""


@dataclass(frozen=True)
class ProviderDescriptor:
    """A provider's DECLARATION of what it is and can do — a claim, not a grant.

    Matches ``schemas/provider_descriptor.v1.json``. ``authority_claims`` must be
    empty: a provider descriptor never declares authority.
    """

    provider_id: str
    provider_kind: str
    capabilities: frozenset[str] = frozenset()
    version: str = "0"
    display_name: str = ""
    #: AdapterCapabilities-shaped flags that are True (subset of the 6 support_* keys).
    runtime_capabilities: frozenset[str] = frozenset()
    custody_claims: frozenset[str] = frozenset()
    authority_claims: tuple[str, ...] = ()

    def digest(self) -> str:
        """Content-addressed digest over the declaration body (stable, versioned)."""
        body = {
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "capabilities": sorted(self.capabilities),
            "version": self.version,
            "runtime_capabilities": sorted(self.runtime_capabilities),
            "custody_claims": sorted(self.custody_claims),
            "authority_claims": list(self.authority_claims),
        }
        return "sha256:" + content_hash(canonical_json(body))

    def to_schema_dict(self) -> dict:
        """Serialize to the provider_descriptor.v1 wire shape (for validation)."""
        out: dict = {
            "schema_version": "provider_descriptor.v1",
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "capabilities": sorted(self.capabilities),
            "authority_claims": list(self.authority_claims),
        }
        if self.display_name:
            out["display_name"] = self.display_name
        if self.version:
            out["version"] = self.version
        if self.runtime_capabilities:
            out["runtime_capabilities"] = {k: True for k in sorted(self.runtime_capabilities)}
        if self.custody_claims:
            out["custody_claims"] = {k: True for k in sorted(self.custody_claims)}
        return out


def check_structural_conformance(d: ProviderDescriptor) -> list[str]:
    """Return structural violations (empty list => STRUCTURAL conformant).

    Descriptor-level ONLY — this proves nothing about runtime behavior. It is the
    most a registry can verify from a declaration alone.
    """
    problems: list[str] = []
    if not d.provider_id.strip():
        problems.append("provider_id is empty")
    if d.provider_kind not in PROVIDER_KINDS:
        problems.append(f"unknown provider_kind {d.provider_kind!r}")
    bad_caps = sorted(set(d.capabilities) - _CAPABILITY_VALUES)
    if bad_caps:
        problems.append(f"unknown capabilities {bad_caps} (not in chain_gate.CapabilityClass)")
    if d.authority_claims:
        problems.append("authority_claims must be empty (a provider descriptor never declares authority)")
    return problems


@dataclass(frozen=True)
class RegistryEntry:
    """A filed declaration plus how far it has been checked. Not a trust record."""

    descriptor: ProviderDescriptor
    conformance: ConformanceLevel
    revoked: bool = False


class ProviderRegistry:
    """A phone book of provider DECLARATIONS — routing eligibility only, never
    trust. Deliberately has no admit/authorize/trust/grant method: AG dispatch is
    the sole decider, and a lookup result is a candidate list, not a permission.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register(self, descriptor: ProviderDescriptor) -> RegistryEntry:
        """File a provider's declaration. Fail-closed: a structurally invalid
        descriptor is REJECTED, never stored. Registration confers no trust and no
        authority — it records a claim that passed structural checks. Replaces any
        prior descriptor for the same ``provider_id`` (freshness by version).
        """
        problems = check_structural_conformance(descriptor)
        if problems:
            raise DescriptorRejected("; ".join(problems))
        entry = RegistryEntry(descriptor=descriptor, conformance=ConformanceLevel.STRUCTURAL)
        self._entries[descriptor.provider_id] = entry
        return entry

    def get(self, provider_id: str) -> RegistryEntry | None:
        return self._entries.get(provider_id)

    def unregister(self, provider_id: str) -> bool:
        return self._entries.pop(provider_id, None) is not None

    def revoke(self, provider_id: str) -> bool:
        """Drop a provider from routing eligibility; the entry stays for audit.
        Returns False if the provider is unknown or already revoked."""
        e = self._entries.get(provider_id)
        if e is None or e.revoked:
            return False
        self._entries[provider_id] = RegistryEntry(
            descriptor=e.descriptor, conformance=e.conformance, revoked=True
        )
        return True

    def candidates_for(
        self,
        *,
        capability_requirements: Iterable[str] = (),
        provider_kind: str | None = None,
    ) -> list[ProviderDescriptor]:
        """ROUTING ELIGIBILITY ONLY — never a grant. Known, non-revoked providers
        whose DECLARED capabilities cover the requirements (and match the kind if
        given). AG dispatch still decides; this is a candidate list, not permission.
        """
        req = set(capability_requirements)
        out = [
            e.descriptor
            for e in self._entries.values()
            if not e.revoked
            and (provider_kind is None or e.descriptor.provider_kind == provider_kind)
            and req.issubset(e.descriptor.capabilities)
        ]
        return sorted(out, key=lambda d: d.provider_id)

    def entries(self, *, include_revoked: bool = False) -> list[RegistryEntry]:
        return sorted(
            (e for e in self._entries.values() if include_revoked or not e.revoked),
            key=lambda e: e.descriptor.provider_id,
        )
