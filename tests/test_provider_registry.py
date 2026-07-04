# SPDX-License-Identifier: Apache-2.0
"""Provider registry (Slice 2) — descriptors only.

Pins the load-bearing properties: a descriptor is a declaration not a grant;
authority is fail-closed (empty by construction); registration confers no trust
(no admit/authorize/grant method exists); revocation drops routing eligibility;
freshness is by version; and a serialized descriptor validates against the DRAFT
provider_descriptor.v1 schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.provider_registry import (
    ConformanceLevel,
    DescriptorRejected,
    ProviderDescriptor,
    ProviderRegistry,
    check_structural_conformance,
)

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "provider_descriptor.v1.json"


def _desc(**kw) -> ProviderDescriptor:
    base = dict(provider_id="prov-x", provider_kind="execution_harness", capabilities=frozenset({"file_write"}))
    base.update(kw)
    return ProviderDescriptor(**base)


class TestStructuralConformance:
    def test_valid_descriptor_has_no_violations(self):
        assert check_structural_conformance(_desc()) == []

    def test_authority_claims_rejected(self):
        problems = check_structural_conformance(_desc(authority_claims=("admit",)))
        assert any("authority_claims must be empty" in p for p in problems)

    def test_unknown_kind_rejected(self):
        problems = check_structural_conformance(_desc(provider_kind="overlord"))
        assert any("unknown provider_kind" in p for p in problems)

    def test_unknown_capability_rejected(self):
        problems = check_structural_conformance(_desc(capabilities=frozenset({"mind_control"})))
        assert any("unknown capabilities" in p for p in problems)


class TestRegistry:
    def test_register_valid_is_structural(self):
        r = ProviderRegistry()
        entry = r.register(_desc())
        assert entry.conformance is ConformanceLevel.STRUCTURAL
        assert r.get("prov-x").descriptor.provider_id == "prov-x"

    def test_register_authority_claim_is_fail_closed(self):
        r = ProviderRegistry()
        with pytest.raises(DescriptorRejected):
            r.register(_desc(authority_claims=("authorize",)))
        assert r.get("prov-x") is None  # never stored

    def test_register_unknown_kind_rejected(self):
        r = ProviderRegistry()
        with pytest.raises(DescriptorRejected):
            r.register(_desc(provider_kind="overlord"))

    def test_registration_confers_no_trust_or_authority(self):
        # The registry is a phone book, not a court: no grant surface may exist.
        r = ProviderRegistry()
        for forbidden in ("admit", "authorize", "trust", "grant", "approve"):
            assert not hasattr(r, forbidden), f"registry must not expose {forbidden}()"

    def test_candidates_require_capability_coverage(self):
        r = ProviderRegistry()
        r.register(_desc(provider_id="writer", capabilities=frozenset({"file_write", "file_read"})))
        r.register(_desc(provider_id="reader", capabilities=frozenset({"file_read"})))
        got = [d.provider_id for d in r.candidates_for(capability_requirements={"file_write"})]
        assert got == ["writer"]

    def test_candidates_filter_by_kind(self):
        r = ProviderRegistry()
        r.register(_desc(provider_id="harness", provider_kind="execution_harness", capabilities=frozenset({"code_exec"})))
        r.register(_desc(provider_id="xform", provider_kind="transform_provider", capabilities=frozenset({"code_exec"})))
        got = [d.provider_id for d in r.candidates_for(provider_kind="transform_provider")]
        assert got == ["xform"]

    def test_revoke_drops_routing_but_keeps_audit(self):
        r = ProviderRegistry()
        r.register(_desc(provider_id="p", capabilities=frozenset({"file_read"})))
        assert r.revoke("p") is True
        assert r.candidates_for(capability_requirements={"file_read"}) == []
        assert r.get("p") is not None  # still known for audit
        assert r.get("p").revoked is True

    def test_revoke_unknown_or_repeat_is_false(self):
        r = ProviderRegistry()
        assert r.revoke("ghost") is False
        r.register(_desc(provider_id="p"))
        assert r.revoke("p") is True
        assert r.revoke("p") is False  # already revoked

    def test_reregister_replaces_by_version_freshness(self):
        r = ProviderRegistry()
        r.register(_desc(provider_id="p", version="1", capabilities=frozenset({"file_read"})))
        r.register(_desc(provider_id="p", version="2", capabilities=frozenset({"file_write"})))
        assert r.get("p").descriptor.version == "2"
        # the stale v1 declaration cannot silently persist
        assert r.candidates_for(capability_requirements={"file_read"}) == []
        assert [d.provider_id for d in r.candidates_for(capability_requirements={"file_write"})] == ["p"]

    def test_digest_is_stable_and_versioned(self):
        a = _desc(version="1")
        b = _desc(version="1")
        c = _desc(version="2")
        assert a.digest() == b.digest()
        assert a.digest() != c.digest()
        assert a.digest().startswith("sha256:")


class TestSchemaConformance:
    def test_descriptor_validates_against_v1_schema(self):
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads(_SCHEMA_PATH.read_text())
        d = _desc(
            display_name="Example",
            runtime_capabilities=frozenset({"supports_structured_events", "supports_graceful_shutdown"}),
            custody_claims=frozenset({"artifact_manifest", "stdout_digest"}),
        )
        jsonschema.Draft202012Validator(schema).validate(d.to_schema_dict())

    def test_authority_claim_descriptor_fails_schema(self):
        # Belt-and-suspenders: the wire schema also refuses authority (maxItems 0).
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads(_SCHEMA_PATH.read_text())
        payload = _desc().to_schema_dict()
        payload["authority_claims"] = ["authorize"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(payload)
