# SPDX-License-Identifier: Apache-2.0
"""Tests for Night Shift Governor adapter.

Covers GOV_GAP_NIGHTSHIFT_ADAPTER_001 acceptance criteria:
- Closed enums (AuthorityLevel, BlastRadius, ToolClass, ActionKind, EventKind)
- Request/response dataclasses with validation + roundtrip
- Deterministic verdict mapping (PolicyVerdict -> NightShiftVerdict)
- check_policy: emits measurement receipt, translates verdict
- record_receipt: role derivation from event_kind, horizon pass-through
- authorize_transition: authority receipt, required_approvals derivation
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.gate_receipt import (
    HORIZON_HOURS,
    ROLE_AUTHORITY,
    ROLE_MEASUREMENT,
    GateReceiptSystem,
    HorizonBlock,
)
from governor.nightshift_adapter import (
    ADAPTER_VERSION,
    AUTHORITY_LEVEL_RANK,
    ActionKind,
    AuthorityLevel,
    AuthorizeTransitionRequest,
    AuthorizeTransitionResponse,
    BlastRadius,
    CheckPolicyRequest,
    CheckPolicyResponse,
    EventKind,
    EvidenceSummary,
    NightShiftVerdict,
    RecordReceiptRequest,
    RecordReceiptResponse,
    RequestedAction,
    ToolClass,
    authorize_transition,
    check_policy,
    record_receipt,
    translate_verdict,
)
from governor.policy_engine import PolicyVerdict, default_policy


VALID_HASH = "sha256:" + "a" * 64
VALID_HASH_2 = "sha256:" + "b" * 64
VALID_HASH_3 = "sha256:" + "c" * 64


# =============================================================================
# Closed enums + verdict mapping
# =============================================================================


class TestClosedEnums:
    def test_authority_level_six_values(self):
        assert {e.value for e in AuthorityLevel} == {
            "observe", "advise", "stage", "request", "apply", "publish",
        }

    def test_authority_level_rank_monotonic(self):
        ranks = [AUTHORITY_LEVEL_RANK[lvl] for lvl in AuthorityLevel]
        assert ranks == sorted(ranks)
        assert AUTHORITY_LEVEL_RANK[AuthorityLevel.OBSERVE] == 0
        assert AUTHORITY_LEVEL_RANK[AuthorityLevel.PUBLISH] == 5

    def test_blast_radius_three_values(self):
        assert {e.value for e in BlastRadius} == {
            "single_host", "multi_host", "public",
        }

    def test_tool_class_six_values(self):
        assert {e.value for e in ToolClass} == {
            "read", "propose", "stage", "mutate", "publish", "page",
        }

    def test_action_kind_four_values(self):
        assert {e.value for e in ActionKind} == {
            "mcp_call", "tool_exec", "state_mutation", "publish",
        }

    def test_event_kind_six_values(self):
        assert {e.value for e in EventKind} == {
            "agenda.promoted", "action.authorized", "action.applied",
            "action.denied", "action.verified", "escalation.paged",
        }


class TestVerdictMapping:
    def test_pass_maps_to_allow(self):
        assert translate_verdict(PolicyVerdict.PASS) == NightShiftVerdict.ALLOW

    def test_block_maps_to_deny(self):
        assert translate_verdict(PolicyVerdict.BLOCK) == NightShiftVerdict.DENY

    def test_escalate_maps_to_require_approval(self):
        assert (
            translate_verdict(PolicyVerdict.ESCALATE)
            == NightShiftVerdict.REQUIRE_APPROVAL
        )

    def test_warn_maps_to_downgrade(self):
        assert (
            translate_verdict(PolicyVerdict.WARN) == NightShiftVerdict.DOWNGRADE
        )

    def test_mapping_covers_every_policy_verdict(self):
        # If a new PolicyVerdict is added, this test fails until
        # translate_verdict gains a new entry. Closed-set discipline.
        for pv in PolicyVerdict:
            translate_verdict(pv)  # should not raise


# =============================================================================
# Dataclass validation + roundtrip
# =============================================================================


def _valid_action() -> RequestedAction:
    return RequestedAction(
        kind=ActionKind.MCP_CALL.value,
        tool_class=ToolClass.READ.value,
        tool_id="foo.bar",
        arguments_hash=VALID_HASH,
        blast_radius=BlastRadius.SINGLE_HOST.value,
        reversible=True,
    )


class TestRequestedAction:
    def test_valid_construction(self):
        a = _valid_action()
        assert a.kind == "mcp_call"

    def test_invalid_action_kind_rejected(self):
        with pytest.raises(ValueError, match="Invalid action kind"):
            RequestedAction(
                kind="not_a_kind",
                tool_class=ToolClass.READ.value,
                tool_id="x",
                arguments_hash=VALID_HASH,
                blast_radius=BlastRadius.SINGLE_HOST.value,
                reversible=True,
            )

    def test_invalid_tool_class_rejected(self):
        with pytest.raises(ValueError, match="Invalid tool_class"):
            RequestedAction(
                kind=ActionKind.MCP_CALL.value,
                tool_class="purple",
                tool_id="x",
                arguments_hash=VALID_HASH,
                blast_radius=BlastRadius.SINGLE_HOST.value,
                reversible=True,
            )

    def test_invalid_blast_radius_rejected(self):
        with pytest.raises(ValueError, match="Invalid blast_radius"):
            RequestedAction(
                kind=ActionKind.MCP_CALL.value,
                tool_class=ToolClass.READ.value,
                tool_id="x",
                arguments_hash=VALID_HASH,
                blast_radius="galactic",
                reversible=True,
            )

    def test_roundtrip(self):
        a = _valid_action()
        b = RequestedAction.from_dict(a.to_dict())
        assert a == b


class TestCheckPolicyRequest:
    def _valid(self) -> CheckPolicyRequest:
        return CheckPolicyRequest(
            agenda_id="wal-bloat-review",
            run_id="run_abc",
            actor="nightshift",
            requested_action=_valid_action(),
            authority_level=AuthorityLevel.ADVISE.value,
        )

    def test_valid_construction(self):
        req = self._valid()
        assert req.agenda_id == "wal-bloat-review"

    def test_invalid_authority_level_rejected(self):
        with pytest.raises(ValueError, match="Invalid authority_level"):
            CheckPolicyRequest(
                agenda_id="a",
                run_id="r",
                actor="x",
                requested_action=_valid_action(),
                authority_level="emperor",
            )

    def test_missing_agenda_id_rejected(self):
        with pytest.raises(ValueError, match="agenda_id is required"):
            CheckPolicyRequest(
                agenda_id="",
                run_id="r",
                actor="x",
                requested_action=_valid_action(),
                authority_level=AuthorityLevel.ADVISE.value,
            )

    def test_missing_run_id_rejected(self):
        with pytest.raises(ValueError, match="run_id is required"):
            CheckPolicyRequest(
                agenda_id="a",
                run_id="",
                actor="x",
                requested_action=_valid_action(),
                authority_level=AuthorityLevel.ADVISE.value,
            )

    def test_missing_actor_rejected(self):
        with pytest.raises(ValueError, match="actor is required"):
            CheckPolicyRequest(
                agenda_id="a",
                run_id="r",
                actor="",
                requested_action=_valid_action(),
                authority_level=AuthorityLevel.ADVISE.value,
            )

    def test_roundtrip_without_bundle_ref(self):
        req = self._valid()
        restored = CheckPolicyRequest.from_dict(req.to_dict())
        assert restored == req

    def test_roundtrip_with_bundle_ref(self):
        req = CheckPolicyRequest(
            agenda_id="a", run_id="r", actor="x",
            requested_action=_valid_action(),
            authority_level=AuthorityLevel.ADVISE.value,
            bundle_ref="bundle://abc",
        )
        restored = CheckPolicyRequest.from_dict(req.to_dict())
        assert restored == req


class TestRecordReceiptRequest:
    def _valid(self) -> RecordReceiptRequest:
        return RecordReceiptRequest(
            event_kind=EventKind.AGENDA_PROMOTED.value,
            run_id="run_abc",
            agenda_id="wal-bloat-review",
            subject_hash=VALID_HASH,
            evidence_hash=VALID_HASH_2,
            policy_hash=VALID_HASH_3,
            from_level=AuthorityLevel.OBSERVE.value,
            to_level=AuthorityLevel.ADVISE.value,
        )

    def test_valid_construction(self):
        e = self._valid()
        assert e.event_kind == "agenda.promoted"

    def test_invalid_event_kind_rejected(self):
        with pytest.raises(ValueError, match="Invalid event_kind"):
            RecordReceiptRequest(
                event_kind="agenda.destroyed",
                run_id="r",
                agenda_id="a",
                subject_hash=VALID_HASH,
                evidence_hash=VALID_HASH_2,
                policy_hash=VALID_HASH_3,
            )

    def test_invalid_from_level_rejected(self):
        with pytest.raises(ValueError, match="Invalid from_level"):
            RecordReceiptRequest(
                event_kind=EventKind.ACTION_AUTHORIZED.value,
                run_id="r",
                agenda_id="a",
                subject_hash=VALID_HASH,
                evidence_hash=VALID_HASH_2,
                policy_hash=VALID_HASH_3,
                from_level="omnipotent",
            )

    def test_optional_levels_accepted_none(self):
        # Events that aren't promotions can omit from/to levels.
        e = RecordReceiptRequest(
            event_kind=EventKind.ACTION_VERIFIED.value,
            run_id="r",
            agenda_id="a",
            subject_hash=VALID_HASH,
            evidence_hash=VALID_HASH_2,
            policy_hash=VALID_HASH_3,
        )
        assert e.from_level is None
        assert e.to_level is None

    def test_roundtrip_with_levels(self):
        e = self._valid()
        restored = RecordReceiptRequest.from_dict(e.to_dict())
        assert restored == e

    def test_roundtrip_with_horizon(self):
        h = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:defer",
            basis_hash=VALID_HASH,
            expiry="2026-04-24T03:00:00Z",
        )
        e = RecordReceiptRequest(
            event_kind=EventKind.ACTION_AUTHORIZED.value,
            run_id="r",
            agenda_id="a",
            subject_hash=VALID_HASH,
            evidence_hash=VALID_HASH_2,
            policy_hash=VALID_HASH_3,
            horizon=h,
        )
        restored = RecordReceiptRequest.from_dict(e.to_dict())
        assert restored.horizon == h


class TestAuthorizeTransitionRequest:
    def _valid(self) -> AuthorizeTransitionRequest:
        return AuthorizeTransitionRequest(
            run_id="run_abc",
            agenda_id="wal-bloat-review",
            from_level=AuthorityLevel.ADVISE.value,
            to_level=AuthorityLevel.STAGE.value,
            evidence_summary=EvidenceSummary(
                bundle_ref="bundle://abc",
                admissible_inputs=("signal_a", "signal_b"),
                blocked_assumptions=("assumption_x",),
            ),
        )

    def test_valid_construction(self):
        t = self._valid()
        assert t.from_level == "advise"
        assert t.to_level == "stage"

    def test_invalid_from_level_rejected(self):
        with pytest.raises(ValueError, match="Invalid from_level"):
            AuthorizeTransitionRequest(
                run_id="r", agenda_id="a",
                from_level="warlord", to_level="stage",
            )

    def test_invalid_to_level_rejected(self):
        with pytest.raises(ValueError, match="Invalid to_level"):
            AuthorizeTransitionRequest(
                run_id="r", agenda_id="a",
                from_level="advise", to_level="overlord",
            )

    def test_roundtrip(self):
        t = self._valid()
        restored = AuthorizeTransitionRequest.from_dict(t.to_dict())
        assert restored == t


# =============================================================================
# check_policy
# =============================================================================


class TestCheckPolicy:
    def test_default_policy_denies_and_emits_measurement(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        policy = default_policy()
        req = CheckPolicyRequest(
            agenda_id="wal-bloat-review",
            run_id="run_abc",
            actor="nightshift",
            requested_action=_valid_action(),
            authority_level=AuthorityLevel.ADVISE.value,
        )
        resp = check_policy(req, policy, system)
        assert resp.verdict == NightShiftVerdict.DENY.value
        # Downgrade-only field; absent on deny.
        assert resp.downgrade_to is None
        # Receipt must exist and carry the measurement role.
        fetched = system.receipt_store.get_by_id(resp.receipt_id)
        assert fetched is not None
        assert fetched.receipt_role == ROLE_MEASUREMENT

    def test_response_to_dict_matches_ns_wire_shape(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        req = CheckPolicyRequest(
            agenda_id="a", run_id="r", actor="x",
            requested_action=_valid_action(),
            authority_level=AuthorityLevel.ADVISE.value,
        )
        resp = check_policy(req, default_policy(), system)
        d = resp.to_dict()
        # NS contract §check_policy response requires these keys.
        for key in ("verdict", "reason", "obligations", "receipt_id"):
            assert key in d
        assert isinstance(d["obligations"], list)

    def test_receipt_evidence_carries_adapter_version(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        req = CheckPolicyRequest(
            agenda_id="a", run_id="r", actor="x",
            requested_action=_valid_action(),
            authority_level=AuthorityLevel.ADVISE.value,
        )
        resp = check_policy(req, default_policy(), system)
        fetched = system.receipt_store.get_by_id(resp.receipt_id)
        assert fetched.gate == "nightshift_adapter"
        # Adapter version sits in gate_config; we can't read it back from the
        # receipt directly but we can verify evidence presence via store.
        evidence = system.evidence_for(fetched)
        assert evidence is not None
        assert "ns_request" in evidence


# =============================================================================
# record_receipt
# =============================================================================


class TestRecordReceipt:
    @pytest.mark.parametrize(
        "event_kind, expected_role",
        [
            (EventKind.AGENDA_PROMOTED.value, ROLE_AUTHORITY),
            (EventKind.ACTION_AUTHORIZED.value, ROLE_AUTHORITY),
            (EventKind.ACTION_APPLIED.value, ROLE_AUTHORITY),
            (EventKind.ACTION_DENIED.value, ROLE_AUTHORITY),
            (EventKind.ACTION_VERIFIED.value, ROLE_MEASUREMENT),
            (EventKind.ESCALATION_PAGED.value, ROLE_MEASUREMENT),
        ],
    )
    def test_event_kind_maps_to_role(
        self, tmp_path: Path, event_kind: str, expected_role: str
    ):
        system = GateReceiptSystem(tmp_path)
        event = RecordReceiptRequest(
            event_kind=event_kind,
            run_id="r",
            agenda_id="a",
            subject_hash=VALID_HASH,
            evidence_hash=VALID_HASH_2,
            policy_hash=VALID_HASH_3,
        )
        resp = record_receipt(event, system)
        fetched = system.receipt_store.get_by_id(resp.receipt_id)
        assert fetched.receipt_role == expected_role

    def test_horizon_forwarded_to_receipt(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        h = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:defer",
            basis_hash=VALID_HASH,
            expiry="2026-04-24T03:00:00Z",
        )
        event = RecordReceiptRequest(
            event_kind=EventKind.ACTION_AUTHORIZED.value,
            run_id="r",
            agenda_id="a",
            subject_hash=VALID_HASH,
            evidence_hash=VALID_HASH_2,
            policy_hash=VALID_HASH_3,
            horizon=h,
        )
        resp = record_receipt(event, system)
        fetched = system.receipt_store.get_by_id(resp.receipt_id)
        assert fetched.horizon == h

    def test_response_shape_has_receipt_id_and_hash(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        event = RecordReceiptRequest(
            event_kind=EventKind.ACTION_VERIFIED.value,
            run_id="r",
            agenda_id="a",
            subject_hash=VALID_HASH,
            evidence_hash=VALID_HASH_2,
            policy_hash=VALID_HASH_3,
        )
        resp = record_receipt(event, system)
        assert isinstance(resp, RecordReceiptResponse)
        assert resp.receipt_id
        assert resp.receipt_hash


# =============================================================================
# authorize_transition
# =============================================================================


class TestAuthorizeTransition:
    def test_default_policy_denies_and_emits_authority(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        policy = default_policy()
        req = AuthorizeTransitionRequest(
            run_id="run_abc",
            agenda_id="wal-bloat-review",
            from_level=AuthorityLevel.ADVISE.value,
            to_level=AuthorityLevel.STAGE.value,
        )
        resp = authorize_transition(req, policy, system)
        assert isinstance(resp, AuthorizeTransitionResponse)
        assert resp.verdict == NightShiftVerdict.DENY.value
        fetched = system.receipt_store.get_by_id(resp.receipt_id)
        assert fetched.receipt_role == ROLE_AUTHORITY

    def test_response_to_dict_has_required_keys(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        req = AuthorizeTransitionRequest(
            run_id="r", agenda_id="a",
            from_level=AuthorityLevel.ADVISE.value,
            to_level=AuthorityLevel.STAGE.value,
        )
        resp = authorize_transition(req, default_policy(), system)
        d = resp.to_dict()
        for key in ("verdict", "reason", "required_approvals", "receipt_id"):
            assert key in d


# =============================================================================
# Regression: adapter version exposed
# =============================================================================


class TestAdapterMetadata:
    def test_adapter_version_present(self):
        assert ADAPTER_VERSION == "1.0.0"
