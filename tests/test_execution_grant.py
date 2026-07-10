# SPDX-License-Identifier: Apache-2.0
"""S2a — execution-grant activation. Deterministic + idempotent mint;
fail-closed on malformed request; v1 locks the dangerous axes; the minted
grant is consumable by the S1 gate.
"""

from __future__ import annotations

import pytest

from governor.runtime.execution_grant import (
    DERIVATION_VERSION,
    ENFORCEMENT_DECLARED_ONLY,
    ActivationError,
    ExecutionRequest,
    activate_execution_grant,
)
from governor.runtime.grant_use_gate import (
    CommandGrant,
    WidensGrant,
    WithinGrant,
    classify_grant_use,
)


def _req(**kw):
    base = dict(
        write_paths=frozenset({"crates/nightshiftd/src/**", "crates/nightshiftd/tests/**"}),
        commands=(CommandGrant("cargo", ("test",)), CommandGrant("cargo", ("build",))),
        source_plan_digest="sha256:plan",
        approval_witness_digest="sha256:witness",
    )
    base.update(kw)
    return ExecutionRequest(**base)


def test_activation_is_deterministic_and_idempotent():
    a = activate_execution_grant(_req())
    b = activate_execution_grant(_req())
    assert a.grant_id == b.grant_id
    assert a.grant_digest == b.grant_digest
    assert a.grant_id.startswith("sgr_") and a.grant_digest.startswith("sha256:")


def test_digest_is_order_independent():
    a = activate_execution_grant(_req(
        commands=(CommandGrant("cargo", ("test",)), CommandGrant("cargo", ("build",)))))
    b = activate_execution_grant(_req(
        commands=(CommandGrant("cargo", ("build",)), CommandGrant("cargo", ("test",)))))
    assert a.grant_digest == b.grant_digest


def test_different_request_different_grant():
    a = activate_execution_grant(_req())
    b = activate_execution_grant(_req(source_plan_digest="sha256:other"))
    assert a.grant_id != b.grant_id


def test_axes_locked_and_requests_recorded_as_unmet():
    art = activate_execution_grant(_req(network_requested=True, git_requested=True))
    assert art.grant.network_allowed is False
    assert art.grant.git_allowed is False
    assert set(art.unmet_axes) == {"network", "git"}


def test_receipt_body_carries_provenance_and_locks():
    body = activate_execution_grant(_req()).receipt_body()
    assert body["derivation_version"] == DERIVATION_VERSION
    assert body["enforcement"] == ENFORCEMENT_DECLARED_ONLY
    assert body["source_plan_digest"] == "sha256:plan"
    assert body["approval_witness_digest"] == "sha256:witness"
    assert body["network"] == "denied" and body["git"] == "denied"
    assert body["secrets"] == "denied" and body["privilege"] == "denied"
    assert body["commands"] == [
        {"program": "cargo", "argv_prefix": ["build"]},
        {"program": "cargo", "argv_prefix": ["test"]},
    ]


@pytest.mark.parametrize("kw", [
    {"source_plan_digest": ""},
    {"approval_witness_digest": ""},
    {"horizon": "forever"},
])
def test_malformed_request_fails_closed(kw):
    with pytest.raises(ActivationError):
        activate_execution_grant(_req(**kw))


def test_minted_grant_is_consumable_by_s1_gate():
    grant = activate_execution_grant(_req()).grant
    assert isinstance(
        classify_grant_use("Bash", {"command": "cargo test --lib"}, grant), WithinGrant)
    assert isinstance(
        classify_grant_use("Edit", {"file_path": "crates/nightshiftd/src/packet.rs"}, grant),
        WithinGrant)
    # a request the plan asked for but v1 did not grant still widens at use:
    assert isinstance(
        classify_grant_use("Bash", {"command": "curl http://x"}, grant), WidensGrant)
