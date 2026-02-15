"""Tests for the Scope Governor — locality-first policy with escalation receipts."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from governor.scope import (
    AccessMode,
    BridgingRequirement,
    DEFAULT_BRIDGING,
    EscalationRequest,
    EscalationResult,
    EscalationVerdict,
    GrantUsage,
    SPATIAL_LADDER,
    Scope,
    ScopeAxis,
    ScopeGovernor,
    ScopeGrant,
    TEMPORAL_LADDER_MINUTES,
    TimeRange,
    ToolScopeContract,
    check_scope_containment,
    check_time_containment,
    check_tool_scope,
    compute_scope_distance,
    compute_scope_hash,
    evaluate_escalation,
    find_bridging_requirement,
    validate_escalation_shape,
)


# =============================================================================
# Helpers
# =============================================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future_iso(minutes: int = 60) -> str:
    t = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _past_iso(minutes: int = 60) -> str:
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_grant(
    scope_dict: dict | None = None,
    tool_allowlist: list[str] | None = None,
    access_mode: AccessMode = AccessMode.READ,
    expired: bool = False,
    revoked: bool = False,
    axis_widened: str = "service",
    run_id: str = "run-1",
) -> ScopeGrant:
    scope_dict = scope_dict or {"service": "*", "region": "us-east-1"}
    expires = _past_iso(5) if expired else _future_iso(60)
    return ScopeGrant(
        grant_id="grant-test-" + str(id(scope_dict))[-6:],
        run_id=run_id,
        scope=Scope.from_dict(scope_dict),
        tool_allowlist=tool_allowlist,
        access_mode=access_mode,
        expires_at=expires,
        minted_at=_now_iso(),
        reason="test grant",
        evidence_refs=["ref-1"],
        axis_widened=axis_widened,
        revoked=revoked,
        revoked_at=_now_iso() if revoked else None,
    )


_SENTINEL = object()


def _make_contract(
    tool_id: str = "file_read",
    required_axes: list[str] | None = _SENTINEL,
    allowed_axes: list[str] | None = _SENTINEL,
    max_default: dict[str, str] | None = None,
    mutability: AccessMode = AccessMode.READ,
) -> ToolScopeContract:
    return ToolScopeContract(
        tool_id=tool_id,
        required_axes=["service"] if required_axes is _SENTINEL else (required_axes or []),
        allowed_axes=["region", "resource"] if allowed_axes is _SENTINEL else (allowed_axes or []),
        max_default_scope=max_default or {"service": "payments"},
        mutability=mutability,
        description=f"Test contract for {tool_id}",
    )


# =============================================================================
# TestEnums
# =============================================================================


class TestEnums:
    def test_scope_axis_values(self):
        assert ScopeAxis.TENANT.value == "tenant"
        assert ScopeAxis.ENVIRONMENT.value == "environment"
        assert ScopeAxis.REGION.value == "region"
        assert ScopeAxis.SERVICE.value == "service"
        assert ScopeAxis.RESOURCE.value == "resource"
        assert ScopeAxis.TIME_WINDOW.value == "time_window"

    def test_scope_axis_count(self):
        assert len(ScopeAxis) == 6

    def test_access_mode_values(self):
        assert AccessMode.READ.value == "read"
        assert AccessMode.WRITE.value == "write"
        assert AccessMode.EXECUTE.value == "execute"

    def test_access_mode_count(self):
        assert len(AccessMode) == 3

    def test_escalation_verdict_values(self):
        assert EscalationVerdict.ALLOW.value == "allow"
        assert EscalationVerdict.ALLOW_READONLY.value == "allow_readonly"
        assert EscalationVerdict.DENY.value == "deny"

    def test_escalation_verdict_count(self):
        assert len(EscalationVerdict) == 3

    def test_spatial_ladder_order(self):
        assert SPATIAL_LADDER == [
            "resource", "service", "region", "environment", "tenant",
        ]

    def test_temporal_ladder_minutes(self):
        assert TEMPORAL_LADDER_MINUTES["5m"] == 5
        assert TEMPORAL_LADDER_MINUTES["1h"] == 60
        assert TEMPORAL_LADDER_MINUTES["all"] == 525600


# =============================================================================
# TestScope
# =============================================================================


class TestScope:
    def test_construction_empty(self):
        s = Scope()
        assert s.axes == ()
        assert s.axes_dict() == {}

    def test_construction_from_dict(self):
        s = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        assert len(s.axes) == 2
        assert s.get("service") == "payments"
        assert s.get("region") == "us-east-1"

    def test_axes_sorted(self):
        s = Scope.from_dict({"region": "us-east-1", "service": "payments"})
        assert s.axes == (("region", "us-east-1"), ("service", "payments"))

    def test_hash_deterministic(self):
        s1 = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        s2 = Scope.from_dict({"region": "us-east-1", "service": "payments"})
        assert s1.scope_hash() == s2.scope_hash()

    def test_hash_differs_for_different_scopes(self):
        s1 = Scope.from_dict({"service": "payments"})
        s2 = Scope.from_dict({"service": "billing"})
        assert s1.scope_hash() != s2.scope_hash()

    def test_get_absent_returns_none(self):
        s = Scope.from_dict({"service": "payments"})
        assert s.get("region") is None

    def test_widen(self):
        s = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        w = s.widen("region", "*")
        assert w.get("region") == "*"
        assert w.get("service") == "payments"

    def test_widen_adds_axis(self):
        s = Scope.from_dict({"service": "payments"})
        w = s.widen("region", "us-east-1")
        assert w.get("region") == "us-east-1"
        assert w.get("service") == "payments"

    def test_roundtrip(self):
        d = {"service": "payments", "region": "us-east-1", "tenant": "*"}
        s = Scope.from_dict(d)
        assert s.to_dict() == d

    def test_frozen(self):
        s = Scope.from_dict({"service": "payments"})
        with pytest.raises(AttributeError):
            s.axes = ()

    def test_equality(self):
        s1 = Scope.from_dict({"service": "payments"})
        s2 = Scope.from_dict({"service": "payments"})
        assert s1 == s2

    def test_hashable(self):
        s = Scope.from_dict({"service": "payments"})
        d = {s: "test"}
        assert d[s] == "test"

    def test_scope_level_resource(self):
        s = Scope.from_dict({"resource": "host:db12", "service": "payments"})
        assert s.scope_level() == "resource"

    def test_scope_level_service(self):
        s = Scope.from_dict({"resource": "*", "service": "payments"})
        assert s.scope_level() == "service"

    def test_scope_level_global(self):
        s = Scope.from_dict({
            "resource": "*", "service": "*", "region": "*",
            "environment": "*", "tenant": "*",
        })
        assert s.scope_level() == "global"

    def test_scope_level_custom(self):
        s = Scope.from_dict({"foo": "bar"})
        assert s.scope_level() == "custom"

    def test_scope_level_empty(self):
        s = Scope()
        assert s.scope_level() == "custom"

    def test_scope_level_region(self):
        s = Scope.from_dict({
            "resource": "*", "service": "*", "region": "us-east-1",
        })
        assert s.scope_level() == "region"


# =============================================================================
# TestTimeRange
# =============================================================================


class TestTimeRange:
    def test_construction(self):
        tr = TimeRange(
            start="2025-01-01T00:00:00Z",
            end="2025-01-01T01:00:00Z",
        )
        assert tr.start == "2025-01-01T00:00:00Z"

    def test_duration_minutes(self):
        tr = TimeRange(
            start="2025-01-01T00:00:00Z",
            end="2025-01-01T01:30:00Z",
        )
        assert tr.duration_minutes() == 90.0

    def test_contains_yes(self):
        outer = TimeRange("2025-01-01T00:00:00Z", "2025-01-01T02:00:00Z")
        inner = TimeRange("2025-01-01T00:30:00Z", "2025-01-01T01:30:00Z")
        assert outer.contains(inner)

    def test_contains_no(self):
        outer = TimeRange("2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z")
        inner = TimeRange("2025-01-01T00:30:00Z", "2025-01-01T01:30:00Z")
        assert not outer.contains(inner)

    def test_contains_exact(self):
        tr = TimeRange("2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z")
        assert tr.contains(tr)

    def test_scope_value_roundtrip(self):
        tr = TimeRange("2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z")
        val = tr.to_scope_value()
        assert "/" in val
        tr2 = TimeRange.from_scope_value(val)
        assert tr2.start == tr.start
        assert tr2.end == tr.end

    def test_last_minutes(self):
        tr = TimeRange.last_minutes(30)
        assert tr.duration_minutes() == pytest.approx(30.0, abs=1.0)

    def test_invalid_iso(self):
        with pytest.raises(ValueError):
            TimeRange(start="not-a-date", end="2025-01-01T00:00:00Z")


# =============================================================================
# TestToolScopeContract
# =============================================================================


class TestToolScopeContract:
    def test_construction(self):
        c = _make_contract()
        assert c.tool_id == "file_read"
        assert "service" in c.required_axes

    def test_all_permitted_axes(self):
        c = _make_contract(
            required_axes=["service"],
            allowed_axes=["region", "resource"],
        )
        assert c.all_permitted_axes() == {"service", "region", "resource"}

    def test_roundtrip(self):
        c = _make_contract()
        d = c.to_dict()
        c2 = ToolScopeContract.from_dict(d)
        assert c2.tool_id == c.tool_id
        assert c2.required_axes == c.required_axes
        assert c2.allowed_axes == c.allowed_axes
        assert c2.mutability == c.mutability

    def test_mutability_preserved(self):
        c = _make_contract(mutability=AccessMode.WRITE)
        assert c.mutability == AccessMode.WRITE

    def test_description_default(self):
        c = ToolScopeContract(
            tool_id="t", required_axes=[], allowed_axes=[],
            max_default_scope={}, mutability=AccessMode.READ,
        )
        assert c.description == ""

    def test_description_preserved(self):
        c = _make_contract()
        d = c.to_dict()
        c2 = ToolScopeContract.from_dict(d)
        assert c2.description == c.description

    def test_empty_axes(self):
        c = ToolScopeContract(
            tool_id="t", required_axes=[], allowed_axes=[],
            max_default_scope={}, mutability=AccessMode.READ,
        )
        assert c.all_permitted_axes() == set()

    def test_overlapping_axes(self):
        c = _make_contract(
            required_axes=["service", "region"],
            allowed_axes=["region", "resource"],
        )
        assert c.all_permitted_axes() == {"service", "region", "resource"}


# =============================================================================
# TestScopeGrant
# =============================================================================


class TestScopeGrant:
    def test_construction(self):
        g = _make_grant()
        assert g.run_id == "run-1"
        assert g.use_count == 0

    def test_is_active_default(self):
        g = _make_grant()
        assert g.is_active()

    def test_is_expired(self):
        g = _make_grant(expired=True)
        assert g.is_expired()
        assert not g.is_active()

    def test_is_revoked(self):
        g = _make_grant(revoked=True)
        assert g.revoked
        assert not g.is_active()

    def test_covers_tool_none_allowlist(self):
        g = _make_grant(tool_allowlist=None)
        assert g.covers_tool("anything")

    def test_covers_tool_in_allowlist(self):
        g = _make_grant(tool_allowlist=["file_read", "file_write"])
        assert g.covers_tool("file_read")
        assert not g.covers_tool("exec_cmd")

    def test_covers_scope(self):
        g = _make_grant(scope_dict={"service": "*", "region": "us-east-1"})
        assert g.covers_scope(
            Scope.from_dict({"service": "payments", "region": "us-east-1"})
        )

    def test_covers_scope_fails(self):
        g = _make_grant(scope_dict={"service": "payments"})
        assert not g.covers_scope(
            Scope.from_dict({"service": "payments", "region": "us-east-1"})
        )

    def test_record_use(self):
        g = _make_grant()
        assert g.use_count == 0
        g.record_use()
        assert g.use_count == 1
        g.record_use()
        assert g.use_count == 2

    def test_roundtrip(self):
        g = _make_grant()
        d = g.to_dict()
        g2 = ScopeGrant.from_dict(d)
        assert g2.grant_id == g.grant_id
        assert g2.scope == g.scope
        assert g2.access_mode == g.access_mode

    def test_roundtrip_with_revocation(self):
        g = _make_grant(revoked=True)
        d = g.to_dict()
        g2 = ScopeGrant.from_dict(d)
        assert g2.revoked is True
        assert g2.revoked_at is not None

    def test_roundtrip_with_use_count(self):
        g = _make_grant()
        g.record_use()
        g.record_use()
        d = g.to_dict()
        g2 = ScopeGrant.from_dict(d)
        assert g2.use_count == 2


# =============================================================================
# TestEscalationRequest
# =============================================================================


class TestEscalationRequest:
    def test_construction(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="need wider scope",
            evidence_refs=["ref-1"],
        )
        assert req.ttl_minutes == 60

    def test_roundtrip(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="test",
            evidence_refs=["ref-1", "ref-2"],
            tool_id="file_read",
            requested_mode=AccessMode.WRITE,
            ttl_minutes=30,
        )
        d = req.to_dict()
        req2 = EscalationRequest.from_dict(d)
        assert req2.from_scope == req.from_scope
        assert req2.to_scope == req.to_scope
        assert req2.ttl_minutes == 30
        assert req2.tool_id == "file_read"

    def test_default_mode(self):
        req = EscalationRequest(
            from_scope=Scope(), to_scope=Scope(),
            reason="", evidence_refs=[],
        )
        assert req.requested_mode == AccessMode.READ

    def test_default_tool_id(self):
        req = EscalationRequest(
            from_scope=Scope(), to_scope=Scope(),
            reason="", evidence_refs=[],
        )
        assert req.tool_id is None

    def test_evidence_refs_list(self):
        req = EscalationRequest(
            from_scope=Scope(), to_scope=Scope(),
            reason="", evidence_refs=["a", "b", "c"],
        )
        assert len(req.evidence_refs) == 3

    def test_frozen(self):
        req = EscalationRequest(
            from_scope=Scope(), to_scope=Scope(),
            reason="", evidence_refs=[],
        )
        with pytest.raises(AttributeError):
            req.reason = "new"


# =============================================================================
# TestBridgingRequirement
# =============================================================================


class TestBridgingRequirement:
    def test_construction(self):
        br = BridgingRequirement("resource", "service", "resource", 1)
        assert br.from_level == "resource"
        assert br.to_level == "service"

    def test_roundtrip(self):
        br = BridgingRequirement("service", "region", "service", 2, "desc")
        d = br.to_dict()
        br2 = BridgingRequirement.from_dict(d)
        assert br2.from_level == br.from_level
        assert br2.min_evidence_refs == 2
        assert br2.description == "desc"

    def test_default_evidence(self):
        br = BridgingRequirement("a", "b", "a")
        assert br.min_evidence_refs == 1

    def test_default_bridging_count(self):
        assert len(DEFAULT_BRIDGING) == 4


# =============================================================================
# TestGrantUsage
# =============================================================================


class TestGrantUsage:
    def test_construction(self):
        gu = GrantUsage(
            grant_id="g1", tool_id="file_write",
            scope_hash="abc", access_mode="write",
            used_at="2025-01-01T00:00:00Z",
        )
        assert gu.grant_id == "g1"

    def test_roundtrip(self):
        gu = GrantUsage("g1", "t1", "hash", "write", "2025-01-01T00:00:00Z")
        d = gu.to_dict()
        gu2 = GrantUsage.from_dict(d)
        assert gu2.grant_id == gu.grant_id
        assert gu2.tool_id == gu.tool_id

    def test_frozen(self):
        gu = GrantUsage("g1", "t1", "hash", "read", "2025-01-01T00:00:00Z")
        with pytest.raises(AttributeError):
            gu.grant_id = "g2"

    def test_all_fields(self):
        gu = GrantUsage("g1", "t1", "h1", "execute", "2025-06-01T12:00:00Z")
        d = gu.to_dict()
        assert set(d.keys()) == {
            "grant_id", "tool_id", "scope_hash", "access_mode", "used_at",
        }


# =============================================================================
# TestComputeScopeHash
# =============================================================================


class TestComputeScopeHash:
    def test_canonical(self):
        h = compute_scope_hash(Scope.from_dict({"service": "payments"}))
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_deterministic(self):
        s = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        assert compute_scope_hash(s) == compute_scope_hash(s)

    def test_order_independent(self):
        s1 = Scope.from_dict({"region": "us-east-1", "service": "payments"})
        s2 = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        assert compute_scope_hash(s1) == compute_scope_hash(s2)

    def test_different_scopes_differ(self):
        s1 = Scope.from_dict({"service": "payments"})
        s2 = Scope.from_dict({"service": "billing"})
        assert compute_scope_hash(s1) != compute_scope_hash(s2)

    def test_empty_scope(self):
        h = compute_scope_hash(Scope())
        assert isinstance(h, str)
        assert len(h) == 64


# =============================================================================
# TestContainment — CRITICAL: the real bugs live here
# =============================================================================


class TestContainment:
    def test_absent_axis_fails(self):
        """If container doesn't mention 'region', contained with region fails."""
        container = Scope.from_dict({"service": "payments"})
        contained = Scope.from_dict({
            "service": "payments", "region": "us-east-1",
        })
        assert not container.contains(contained)

    def test_wildcard_allows(self):
        """Explicit wildcard on region allows any region value."""
        container = Scope.from_dict({
            "service": "payments", "region": "*",
        })
        contained = Scope.from_dict({
            "service": "payments", "region": "us-east-1",
        })
        assert container.contains(contained)

    def test_exact_match(self):
        s1 = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        s2 = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        assert s1.contains(s2)

    def test_subset_axes(self):
        """Container has more axes (all matching) — contained is a subset."""
        container = Scope.from_dict({
            "service": "payments", "region": "us-east-1", "tenant": "acme",
        })
        contained = Scope.from_dict({"service": "payments"})
        assert container.contains(contained)

    def test_superset_axes_fails(self):
        """Contained has more axes than container — fails."""
        container = Scope.from_dict({"service": "payments"})
        contained = Scope.from_dict({
            "service": "payments", "region": "us-east-1", "tenant": "acme",
        })
        assert not container.contains(contained)

    def test_disjoint_values(self):
        container = Scope.from_dict({"service": "payments"})
        contained = Scope.from_dict({"service": "billing"})
        assert not container.contains(contained)

    def test_empty_scope_contains_nothing(self):
        """Empty scope = nothing allowed."""
        container = Scope()
        contained = Scope.from_dict({"service": "payments"})
        assert not container.contains(contained)

    def test_empty_contains_empty(self):
        """Empty contains empty (vacuously true)."""
        assert Scope().contains(Scope())

    def test_explicit_global_contains_anything(self):
        """All axes explicit wildcard = global."""
        container = Scope.from_dict({
            "service": "*", "region": "*", "environment": "*", "tenant": "*",
        })
        contained = Scope.from_dict({
            "service": "payments", "region": "us-east-1",
        })
        assert container.contains(contained)

    def test_wildcard_vs_wildcard(self):
        container = Scope.from_dict({"service": "*"})
        contained = Scope.from_dict({"service": "*"})
        assert container.contains(contained)

    def test_time_window_containment(self):
        container = Scope.from_dict({
            "service": "payments",
            "time_window": "2025-01-01T00:00:00Z/2025-01-01T02:00:00Z",
        })
        contained = Scope.from_dict({
            "service": "payments",
            "time_window": "2025-01-01T00:30:00Z/2025-01-01T01:30:00Z",
        })
        assert container.contains(contained)

    def test_time_window_fails(self):
        container = Scope.from_dict({
            "service": "payments",
            "time_window": "2025-01-01T00:00:00Z/2025-01-01T01:00:00Z",
        })
        contained = Scope.from_dict({
            "service": "payments",
            "time_window": "2025-01-01T00:30:00Z/2025-01-01T01:30:00Z",
        })
        assert not container.contains(contained)

    def test_time_window_wildcard(self):
        container = Scope.from_dict({
            "service": "payments", "time_window": "*",
        })
        contained = Scope.from_dict({
            "service": "payments",
            "time_window": "2025-01-01T00:00:00Z/2025-01-01T01:00:00Z",
        })
        assert container.contains(contained)

    def test_mixed_wildcard_and_concrete(self):
        container = Scope.from_dict({
            "service": "*", "region": "us-east-1",
        })
        contained = Scope.from_dict({
            "service": "payments", "region": "us-east-1",
        })
        assert container.contains(contained)

    def test_mixed_wildcard_and_concrete_fails(self):
        container = Scope.from_dict({
            "service": "*", "region": "us-east-1",
        })
        contained = Scope.from_dict({
            "service": "payments", "region": "eu-west-1",
        })
        assert not container.contains(contained)


# =============================================================================
# TestCheckToolScope
# =============================================================================


class TestCheckToolScope:
    def test_within_scope(self):
        tool = _make_contract(
            required_axes=["service"],
            allowed_axes=["region"],
        )
        run = Scope.from_dict({"service": "payments", "region": "*"})
        req = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        ok, err = check_tool_scope(tool, req, run, [])
        assert ok
        assert err is None

    def test_outside_scope(self):
        tool = _make_contract(required_axes=["service"])
        run = Scope.from_dict({"service": "payments"})
        req = Scope.from_dict({"service": "billing"})
        ok, err = check_tool_scope(tool, req, run, [])
        assert not ok
        assert "Mulder prevention" in err

    def test_axis_smuggling_rejected(self):
        """Tool tries to use axis it hasn't declared."""
        tool = _make_contract(
            required_axes=["service"],
            allowed_axes=["region"],
        )
        run = Scope.from_dict({
            "service": "payments", "region": "*", "tenant": "*",
        })
        req = Scope.from_dict({
            "service": "payments", "tenant": "acme",
        })
        ok, err = check_tool_scope(tool, req, run, [])
        assert not ok
        assert "Axis smuggling" in err

    def test_required_axes_missing(self):
        tool = _make_contract(required_axes=["service", "region"])
        run = Scope.from_dict({"service": "payments", "region": "*"})
        req = Scope.from_dict({"service": "payments"})
        ok, err = check_tool_scope(tool, req, run, [])
        assert not ok
        assert "Required axis" in err

    def test_grant_covers_gap(self):
        tool = _make_contract(
            required_axes=["service"],
            allowed_axes=["region"],
        )
        run = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        req = Scope.from_dict({"service": "payments", "region": "us-west-2"})
        grant = _make_grant(
            scope_dict={"service": "payments", "region": "*"},
            axis_widened="region",
        )
        ok, err = check_tool_scope(tool, req, run, [grant])
        assert ok

    def test_expired_grant_ignored(self):
        tool = _make_contract(required_axes=["service"])
        run = Scope.from_dict({"service": "payments"})
        req = Scope.from_dict({"service": "billing"})
        grant = _make_grant(
            scope_dict={"service": "*"},
            expired=True,
        )
        ok, err = check_tool_scope(tool, req, run, [grant])
        assert not ok

    def test_revoked_grant_ignored(self):
        tool = _make_contract(required_axes=["service"])
        run = Scope.from_dict({"service": "payments"})
        req = Scope.from_dict({"service": "billing"})
        grant = _make_grant(
            scope_dict={"service": "*"},
            revoked=True,
        )
        ok, err = check_tool_scope(tool, req, run, [grant])
        assert not ok

    def test_grant_wrong_tool(self):
        tool = _make_contract(
            tool_id="file_read",
            required_axes=["service"],
        )
        run = Scope.from_dict({"service": "payments"})
        req = Scope.from_dict({"service": "billing"})
        grant = _make_grant(
            scope_dict={"service": "*"},
            tool_allowlist=["exec_cmd"],
        )
        ok, err = check_tool_scope(tool, req, run, [grant])
        assert not ok

    def test_multiple_grants_checked(self):
        tool = _make_contract(
            required_axes=["service"],
            allowed_axes=["region"],
        )
        run = Scope.from_dict({"service": "payments", "region": "us-east-1"})
        req = Scope.from_dict({"service": "payments", "region": "eu-west-1"})
        grant_wrong = _make_grant(
            scope_dict={"service": "payments", "region": "us-west-2"},
        )
        grant_right = _make_grant(
            scope_dict={"service": "payments", "region": "*"},
        )
        ok, err = check_tool_scope(tool, req, run, [grant_wrong, grant_right])
        assert ok

    def test_no_axes_tool(self):
        """Tool with no axes — any request with axes fails smuggling check."""
        tool = _make_contract(required_axes=[], allowed_axes=[])
        run = Scope.from_dict({"service": "payments"})
        req = Scope.from_dict({"service": "payments"})
        ok, err = check_tool_scope(tool, req, run, [])
        assert not ok
        assert "Axis smuggling" in err

    def test_no_axes_empty_request(self):
        """Tool and request both have no axes — passes."""
        tool = _make_contract(required_axes=[], allowed_axes=[])
        run = Scope.from_dict({"service": "payments"})
        req = Scope()
        ok, err = check_tool_scope(tool, req, run, [])
        assert ok

    def test_within_max_default(self):
        """Within run scope — doesn't need grant."""
        tool = _make_contract(
            required_axes=["service"],
            max_default={"service": "payments"},
        )
        run = Scope.from_dict({"service": "*"})
        req = Scope.from_dict({"service": "billing"})
        ok, err = check_tool_scope(tool, req, run, [])
        assert ok

    def test_all_required_present_all_allowed_used(self):
        tool = _make_contract(
            required_axes=["service"],
            allowed_axes=["region", "resource"],
        )
        run = Scope.from_dict({
            "service": "*", "region": "*", "resource": "*",
        })
        req = Scope.from_dict({
            "service": "payments", "region": "us-east-1",
            "resource": "host:db12",
        })
        ok, err = check_tool_scope(tool, req, run, [])
        assert ok


# =============================================================================
# TestValidateEscalationShape
# =============================================================================


class TestValidateEscalationShape:
    def test_one_axis_ok(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="widen", evidence_refs=["r1"],
        )
        assert validate_escalation_shape(req) is None

    def test_multi_axis_denied(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "service": "payments", "region": "us-east-1",
            }),
            to_scope=Scope.from_dict({
                "service": "*", "region": "*",
            }),
            reason="widen", evidence_refs=["r1"],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "Multi-axis" in err
        assert "Split" in err

    def test_same_scope_denied(self):
        s = Scope.from_dict({"service": "payments"})
        req = EscalationRequest(
            from_scope=s, to_scope=s,
            reason="", evidence_refs=[],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "No axes changed" in err

    def test_already_wildcard(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "*"}),
            to_scope=Scope.from_dict({"service": "payments"}),
            reason="", evidence_refs=[],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "already wildcard" in err

    def test_axis_introduction(self):
        """Adding a new axis (absent → value) is valid."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({
                "service": "payments", "region": "us-east-1",
            }),
            reason="add region", evidence_refs=["r1"],
        )
        assert validate_escalation_shape(req) is None

    def test_axis_removal_denied(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "service": "payments", "region": "us-east-1",
            }),
            to_scope=Scope.from_dict({"service": "payments"}),
            reason="remove region", evidence_refs=[],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "narrowing" in err

    def test_time_window_widen(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "time_window": "2025-01-01T00:00:00Z/2025-01-01T01:00:00Z",
            }),
            to_scope=Scope.from_dict({
                "time_window": "2025-01-01T00:00:00Z/2025-01-01T02:00:00Z",
            }),
            reason="wider time", evidence_refs=["r1"],
        )
        assert validate_escalation_shape(req) is None

    def test_time_window_narrow_denied(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "time_window": "2025-01-01T00:00:00Z/2025-01-01T02:00:00Z",
            }),
            to_scope=Scope.from_dict({
                "time_window": "2025-01-01T00:00:00Z/2025-01-01T01:00:00Z",
            }),
            reason="narrow", evidence_refs=[],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "not widened" in err

    def test_concrete_to_concrete_pivot_denied(self):
        """Pivoting (concrete → different concrete) is not escalation."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "billing"}),
            reason="pivot", evidence_refs=["r1"],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "pivot" in err

    def test_concrete_to_concrete_non_ladder_also_denied(self):
        """Even non-ladder axes: concrete→concrete is a pivot, not escalation."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({"custom_axis": "value1"}),
            to_scope=Scope.from_dict({"custom_axis": "value2"}),
            reason="pivot", evidence_refs=["r1"],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "pivot" in err

    def test_wildcard_to_concrete_denied(self):
        """Narrowing wildcard → concrete is not escalation."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "*"}),
            to_scope=Scope.from_dict({"service": "payments"}),
            reason="narrow", evidence_refs=[],
        )
        err = validate_escalation_shape(req)
        assert err is not None
        assert "wildcard" in err


# =============================================================================
# TestEvaluateEscalation
# =============================================================================


class TestEvaluateEscalation:
    def test_allow(self):
        """Sufficient evidence → ALLOW."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="need all resources",
            evidence_refs=["ref-1"],
        )
        result = evaluate_escalation(req)
        assert result.verdict == EscalationVerdict.ALLOW
        assert result.grant is not None
        assert result.bridging_satisfied

    def test_deny_insufficient_evidence_read(self):
        """Read mode + insufficient evidence → DENY."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="need all resources",
            evidence_refs=[],  # no evidence
        )
        result = evaluate_escalation(req)
        assert result.verdict == EscalationVerdict.DENY
        assert result.grant is None
        assert not result.bridging_satisfied

    def test_readonly_fallback_write(self):
        """Write mode + insufficient evidence → ALLOW_READONLY."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="need to write",
            evidence_refs=[],
            requested_mode=AccessMode.WRITE,
        )
        result = evaluate_escalation(req)
        assert result.verdict == EscalationVerdict.ALLOW_READONLY
        assert result.grant is not None
        assert result.grant.access_mode == AccessMode.READ  # downgraded

    def test_readonly_fallback_execute(self):
        """Execute mode + insufficient evidence → ALLOW_READONLY."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="need to execute",
            evidence_refs=[],
            requested_mode=AccessMode.EXECUTE,
        )
        result = evaluate_escalation(req)
        assert result.verdict == EscalationVerdict.ALLOW_READONLY

    def test_deny_invalid_shape(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "service": "payments", "region": "us-east-1",
            }),
            to_scope=Scope.from_dict({
                "service": "*", "region": "*",
            }),
            reason="multi-axis",
            evidence_refs=["ref-1", "ref-2"],
        )
        result = evaluate_escalation(req)
        assert result.verdict == EscalationVerdict.DENY
        assert "Multi-axis" in result.reason

    def test_no_bridging_requirement(self):
        """No matching bridging requirement → allow (no constraint)."""
        req = EscalationRequest(
            from_scope=Scope.from_dict({"foo": "bar"}),
            to_scope=Scope.from_dict({"foo": "*"}),
            reason="custom axis",
            evidence_refs=[],
        )
        result = evaluate_escalation(req)
        assert result.verdict == EscalationVerdict.ALLOW

    def test_grant_has_ttl(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="test",
            evidence_refs=["ref-1"],
            ttl_minutes=30,
        )
        result = evaluate_escalation(req)
        assert result.grant is not None
        # Verify TTL is roughly 30 minutes from now
        expires = datetime.fromisoformat(
            result.grant.expires_at.replace("Z", "+00:00")
        )
        now = datetime.now(timezone.utc)
        diff = (expires - now).total_seconds() / 60.0
        assert 29.0 <= diff <= 31.0

    def test_grant_bound_to_tool(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="test",
            evidence_refs=["ref-1"],
            tool_id="file_read",
        )
        result = evaluate_escalation(req)
        assert result.grant is not None
        assert result.grant.tool_allowlist == ["file_read"]

    def test_grant_no_tool(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="test",
            evidence_refs=["ref-1"],
        )
        result = evaluate_escalation(req)
        assert result.grant is not None
        assert result.grant.tool_allowlist is None

    def test_axis_widened_tracked(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="test",
            evidence_refs=["ref-1"],
        )
        result = evaluate_escalation(req)
        assert result.axis_widened == "resource"

    def test_run_id_propagated(self):
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="test",
            evidence_refs=["ref-1"],
        )
        result = evaluate_escalation(req, run_id="my-run")
        assert result.grant.run_id == "my-run"


# =============================================================================
# TestScopeDistance
# =============================================================================


class TestScopeDistance:
    def test_adjacent(self):
        assert compute_scope_distance("resource", "service", SPATIAL_LADDER) == 1

    def test_multi_hop(self):
        assert compute_scope_distance("resource", "tenant", SPATIAL_LADDER) == 4

    def test_same_position(self):
        assert compute_scope_distance("service", "service", SPATIAL_LADDER) == 0

    def test_off_ladder(self):
        assert compute_scope_distance("resource", "custom", SPATIAL_LADDER) == -1

    def test_both_off_ladder(self):
        assert compute_scope_distance("foo", "bar", SPATIAL_LADDER) == -1


# =============================================================================
# TestCheckTimeContainment
# =============================================================================


class TestCheckTimeContainment:
    def test_contained(self):
        outer = TimeRange("2025-01-01T00:00:00Z", "2025-01-01T02:00:00Z")
        inner = TimeRange("2025-01-01T00:30:00Z", "2025-01-01T01:30:00Z")
        assert check_time_containment(outer, inner)

    def test_not_contained(self):
        outer = TimeRange("2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z")
        inner = TimeRange("2025-01-01T00:30:00Z", "2025-01-01T01:30:00Z")
        assert not check_time_containment(outer, inner)


# =============================================================================
# TestScopeGovernor — stateful coordinator
# =============================================================================


class TestScopeGovernor:
    def test_construction(self):
        sg = ScopeGovernor()
        assert sg.get_run_scope() is None
        assert sg.get_contracts() == []

    def test_set_run_scope(self):
        sg = ScopeGovernor()
        s = Scope.from_dict({"service": "payments"})
        sg.set_run_scope(s)
        assert sg.get_run_scope() == s

    def test_register_tool(self):
        sg = ScopeGovernor()
        c = _make_contract()
        sg.register_tool(c)
        assert len(sg.get_contracts()) == 1

    def test_check_tool_no_scope(self):
        sg = ScopeGovernor()
        sg.register_tool(_make_contract())
        ok, err = sg.check_tool("file_read", Scope.from_dict({"service": "x"}))
        assert not ok
        assert "No run scope" in err

    def test_check_tool_no_contract(self):
        sg = ScopeGovernor()
        sg.set_run_scope(Scope.from_dict({"service": "*"}))
        ok, err = sg.check_tool("unknown", Scope.from_dict({"service": "x"}))
        assert not ok
        assert "No contract" in err

    def test_check_tool_within_scope(self):
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "*", "region": "*"}),
        )
        sg.register_tool(_make_contract(
            required_axes=["service"],
            allowed_axes=["region"],
        ))
        ok, err = sg.check_tool(
            "file_read",
            Scope.from_dict({"service": "payments", "region": "us-east-1"}),
        )
        assert ok

    def test_check_tool_outside_scope(self):
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments"}),
        )
        sg.register_tool(_make_contract(required_axes=["service"]))
        ok, err = sg.check_tool(
            "file_read",
            Scope.from_dict({"service": "billing"}),
        )
        assert not ok

    def test_escalate_allow(self):
        sg = ScopeGovernor(run_id="test-run")
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="test",
            evidence_refs=["ref-1"],
        )
        result = sg.escalate(req)
        assert result.verdict == EscalationVerdict.ALLOW
        assert len(sg.get_active_grants()) == 1
        assert len(sg.get_escalation_history()) == 1

    def test_escalate_deny(self):
        sg = ScopeGovernor()
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "service": "payments", "region": "us-east-1",
            }),
            to_scope=Scope.from_dict({
                "service": "*", "region": "*",
            }),
            reason="multi-axis",
            evidence_refs=["ref-1"],
        )
        result = sg.escalate(req)
        assert result.verdict == EscalationVerdict.DENY
        assert len(sg.get_active_grants()) == 0
        assert len(sg.get_escalation_history()) == 1

    def test_escalate_with_receipt(self):
        sg = ScopeGovernor()
        mock_system = MagicMock()
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "receipt-123"
        mock_system.emit.return_value = mock_receipt

        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="test",
            evidence_refs=["ref-1"],
        )
        result = sg.escalate(req, receipt_system=mock_system)
        assert result.receipt_id == "receipt-123"
        mock_system.emit.assert_called_once()

    def test_revoke_grant(self):
        sg = ScopeGovernor()
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="test",
            evidence_refs=["ref-1"],
        )
        result = sg.escalate(req)
        grant_id = result.grant.grant_id
        assert sg.revoke_grant(grant_id, "no longer needed")
        assert len(sg.get_active_grants()) == 0

    def test_revoke_nonexistent(self):
        sg = ScopeGovernor()
        assert not sg.revoke_grant("nonexistent", "reason")

    def test_grant_usage_tracking(self):
        sg = ScopeGovernor()
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="test",
            evidence_refs=["ref-1"],
            requested_mode=AccessMode.WRITE,
        )
        result = sg.escalate(req)
        grant_id = result.grant.grant_id

        scope = Scope.from_dict({"service": "billing"})
        sg.record_grant_usage(grant_id, "file_write", scope, AccessMode.WRITE)
        sg.record_grant_usage(grant_id, "file_write", scope, AccessMode.WRITE)

        usages = sg.get_grant_usages(grant_id)
        assert len(usages) == 2
        all_usages = sg.get_grant_usages()
        assert len(all_usages) == 2

    def test_metrics(self):
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments"}),
        )
        sg.register_tool(_make_contract())
        m = sg.get_metrics()
        assert m["contracts_count"] == 1
        assert m["grants_total"] == 0
        assert m["run_scope_level"] == "service"

    def test_reset(self):
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments"}),
        )
        sg.register_tool(_make_contract())
        sg.reset()
        assert sg.get_run_scope() is None
        assert sg.get_contracts() == []
        assert sg.get_active_grants() == []

    def test_escalate_receipt_failure_graceful(self):
        """Receipt emission failure doesn't block the escalation."""
        sg = ScopeGovernor()
        mock_system = MagicMock()
        mock_system.emit.side_effect = RuntimeError("boom")

        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="test",
            evidence_refs=["ref-1"],
        )
        result = sg.escalate(req, receipt_system=mock_system)
        assert result.verdict == EscalationVerdict.ALLOW
        assert result.receipt_id is None  # failed but didn't crash


# =============================================================================
# TestPersistence
# =============================================================================


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments", "region": "*"}),
            run_id="test-run",
        )
        sg.register_tool(_make_contract())

        # Escalate to get a grant
        req = EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="test",
            evidence_refs=["ref-1"],
        )
        sg.escalate(req)
        sg.save(tmp_path)

        sg2 = ScopeGovernor.load(tmp_path)
        assert sg2.get_run_scope() == sg.get_run_scope()
        assert len(sg2.get_contracts()) == 1
        assert len(sg2.get_all_grants()) == 1
        assert len(sg2.get_escalation_history()) == 1

    def test_load_missing_file(self, tmp_path):
        sg = ScopeGovernor.load(tmp_path)
        assert sg.get_run_scope() is None

    def test_load_corrupt_file(self, tmp_path):
        (tmp_path / "scope.json").write_text("not json")
        sg = ScopeGovernor.load(tmp_path)
        assert sg.get_run_scope() is None

    def test_atomic_write(self, tmp_path):
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments"}),
        )
        sg.save(tmp_path)
        assert (tmp_path / "scope.json").exists()
        assert not (tmp_path / "scope.json.tmp").exists()

    def test_save_load_with_usages(self, tmp_path):
        sg = ScopeGovernor(run_id="test-run")
        req = EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="test",
            evidence_refs=["ref-1"],
            requested_mode=AccessMode.WRITE,
        )
        result = sg.escalate(req)
        sg.record_grant_usage(
            result.grant.grant_id, "file_write",
            Scope.from_dict({"service": "billing"}), AccessMode.WRITE,
        )
        sg.save(tmp_path)

        sg2 = ScopeGovernor.load(tmp_path)
        assert len(sg2.get_grant_usages()) == 1

    def test_save_load_with_bridging(self, tmp_path):
        bridging = [BridgingRequirement("a", "b", "a", 3, "custom")]
        sg = ScopeGovernor(bridging=bridging, ladder=["a", "b", "c"])
        sg.save(tmp_path)

        sg2 = ScopeGovernor.load(tmp_path)
        assert len(sg2._bridging) == 1
        assert sg2._bridging[0].min_evidence_refs == 3
        assert sg2._ladder == ["a", "b", "c"]

    def test_to_dict_from_dict(self):
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments"}),
            run_id="r1",
        )
        sg.register_tool(_make_contract())
        d = sg.to_dict()
        sg2 = ScopeGovernor.from_dict(d)
        assert sg2.get_run_scope() == sg.get_run_scope()
        assert sg2._run_id == "r1"

    def test_overwrite_existing(self, tmp_path):
        sg1 = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments"}),
        )
        sg1.save(tmp_path)

        sg2 = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "billing"}),
        )
        sg2.save(tmp_path)

        sg3 = ScopeGovernor.load(tmp_path)
        assert sg3.get_run_scope().get("service") == "billing"

    def test_schema_version_in_output(self, tmp_path):
        sg = ScopeGovernor()
        d = sg.to_dict()
        assert "schema_version" in d
        assert d["schema_version"] == 1

    def test_schema_version_future_rejected(self, tmp_path):
        (tmp_path / "scope.json").write_text(
            json.dumps({"schema_version": 999})
        )
        with pytest.raises(ValueError, match="newer than supported"):
            ScopeGovernor.load(tmp_path)

    def test_schema_version_missing_defaults_to_1(self):
        """Old files without schema_version load fine (default=1)."""
        d = {"run_scope": {"service": "payments"}}
        sg = ScopeGovernor.from_dict(d)
        assert sg.get_run_scope().get("service") == "payments"


# =============================================================================
# TestScenarios — integration-style tests
# =============================================================================


class TestScenarios:
    def test_expanding_rings(self):
        """Start local, earn wider scope step by step."""
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({
                "resource": "host:db12",
                "service": "payments",
                "region": "us-east-1",
                "environment": "prod",
                "tenant": "acme",
            }),
        )

        # Step 1: resource → *
        r1 = sg.escalate(EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="need all resources",
            evidence_refs=["log-correlation-1"],
        ))
        assert r1.verdict == EscalationVerdict.ALLOW
        assert r1.axis_widened == "resource"

    def test_earned_global(self):
        """Can't go global in one step — multi-axis denied."""
        sg = ScopeGovernor()
        result = sg.escalate(EscalationRequest(
            from_scope=Scope.from_dict({
                "service": "payments", "region": "us-east-1",
            }),
            to_scope=Scope.from_dict({
                "service": "*", "region": "*",
            }),
            reason="just check everything",
            evidence_refs=["some-log"],
        ))
        assert result.verdict == EscalationVerdict.DENY
        assert "Multi-axis" in result.reason

    def test_mulder_denied(self):
        """Tool scope check fails when trying to exceed run scope."""
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments", "region": "*"}),
        )
        sg.register_tool(_make_contract(
            tool_id="db_query",
            required_axes=["service"],
            allowed_axes=["region"],
        ))
        ok, err = sg.check_tool(
            "db_query",
            Scope.from_dict({"service": "billing"}),
        )
        assert not ok
        assert "Mulder prevention" in err

    def test_read_only_compromise(self):
        """Write requested but insufficient evidence → read-only grant."""
        sg = ScopeGovernor()
        result = sg.escalate(EscalationRequest(
            from_scope=Scope.from_dict({
                "resource": "host:db12", "service": "payments",
            }),
            to_scope=Scope.from_dict({
                "resource": "*", "service": "payments",
            }),
            reason="need to patch",
            evidence_refs=[],
            requested_mode=AccessMode.WRITE,
        ))
        assert result.verdict == EscalationVerdict.ALLOW_READONLY
        assert result.grant.access_mode == AccessMode.READ

    def test_grant_expiry(self):
        """Expired grants don't count for tool scope checks."""
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({"service": "payments"}),
        )
        sg.register_tool(_make_contract(required_axes=["service"]))

        # Add an expired grant manually
        expired = _make_grant(
            scope_dict={"service": "*"},
            expired=True,
        )
        sg._grants.append(expired)

        ok, err = sg.check_tool(
            "file_read",
            Scope.from_dict({"service": "billing"}),
        )
        assert not ok

    def test_multi_axis_split(self):
        """Multi-axis escalation rejected with 'split' message."""
        sg = ScopeGovernor()
        result = sg.escalate(EscalationRequest(
            from_scope=Scope.from_dict({
                "service": "payments", "region": "us-east-1",
                "environment": "prod",
            }),
            to_scope=Scope.from_dict({
                "service": "*", "region": "*",
                "environment": "prod",
            }),
            reason="two axes",
            evidence_refs=["r1", "r2"],
        ))
        assert result.verdict == EscalationVerdict.DENY
        assert "Split" in result.reason

    def test_usage_audit_trail(self):
        """Write grants track each usage."""
        sg = ScopeGovernor()
        result = sg.escalate(EscalationRequest(
            from_scope=Scope.from_dict({"service": "payments"}),
            to_scope=Scope.from_dict({"service": "*"}),
            reason="wide access",
            evidence_refs=["ref-1"],
            requested_mode=AccessMode.WRITE,
        ))
        grant_id = result.grant.grant_id

        # Record multiple usages
        for svc in ["billing", "auth", "metrics"]:
            sg.record_grant_usage(
                grant_id, "file_write",
                Scope.from_dict({"service": svc}),
                AccessMode.WRITE,
            )

        usages = sg.get_grant_usages(grant_id)
        assert len(usages) == 3
        # Grant itself tracks count
        grant = [g for g in sg.get_all_grants() if g.grant_id == grant_id][0]
        assert grant.use_count == 3

    def test_empty_scope_locked(self):
        """Empty scope = nothing allowed."""
        sg = ScopeGovernor(run_scope=Scope())
        sg.register_tool(_make_contract(
            required_axes=[],
            allowed_axes=["service"],
        ))
        ok, err = sg.check_tool(
            "file_read",
            Scope.from_dict({"service": "payments"}),
        )
        assert not ok

    def test_axis_smuggling_blocked(self):
        """Tool can't use axes it hasn't declared."""
        sg = ScopeGovernor(
            run_scope=Scope.from_dict({
                "service": "*", "region": "*", "tenant": "*",
            }),
        )
        sg.register_tool(_make_contract(
            tool_id="limited_tool",
            required_axes=["service"],
            allowed_axes=[],
        ))

        ok, err = sg.check_tool(
            "limited_tool",
            Scope.from_dict({"service": "payments", "tenant": "acme"}),
        )
        assert not ok
        assert "Axis smuggling" in err


# =============================================================================
# TestEscalationResult
# =============================================================================


class TestEscalationResult:
    def test_roundtrip(self):
        er = EscalationResult(
            verdict=EscalationVerdict.ALLOW,
            grant=_make_grant(),
            reason="test",
            axis_widened="service",
            bridging_satisfied=True,
            receipt_id="r-123",
            timestamp="2025-01-01T00:00:00Z",
        )
        d = er.to_dict()
        er2 = EscalationResult.from_dict(d)
        assert er2.verdict == EscalationVerdict.ALLOW
        assert er2.axis_widened == "service"
        assert er2.receipt_id == "r-123"

    def test_roundtrip_no_grant(self):
        er = EscalationResult(
            verdict=EscalationVerdict.DENY,
            grant=None,
            reason="denied",
            axis_widened=None,
            bridging_satisfied=False,
        )
        d = er.to_dict()
        er2 = EscalationResult.from_dict(d)
        assert er2.grant is None
        assert er2.verdict == EscalationVerdict.DENY


# =============================================================================
# TestFindBridgingRequirement
# =============================================================================


class TestFindBridgingRequirement:
    def test_finds_match(self):
        f = Scope.from_dict({
            "resource": "host:db12", "service": "payments",
        })
        t = Scope.from_dict({
            "resource": "*", "service": "payments",
        })
        br = find_bridging_requirement(f, t, DEFAULT_BRIDGING)
        assert br is not None
        assert br.from_level == "resource"
        assert br.to_level == "service"

    def test_no_match(self):
        f = Scope.from_dict({"foo": "bar"})
        t = Scope.from_dict({"foo": "*"})
        br = find_bridging_requirement(f, t, DEFAULT_BRIDGING)
        assert br is None

    def test_service_to_region(self):
        f = Scope.from_dict({
            "resource": "*", "service": "payments", "region": "us-east-1",
        })
        t = Scope.from_dict({
            "resource": "*", "service": "*", "region": "us-east-1",
        })
        br = find_bridging_requirement(f, t, DEFAULT_BRIDGING)
        assert br is not None
        assert br.from_level == "service"
        assert br.to_level == "region"

    def test_custom_requirements(self):
        custom = [BridgingRequirement("a", "b", "a", 5, "custom")]
        f = Scope.from_dict({"a": "x"})
        t = Scope.from_dict({"a": "*"})
        br = find_bridging_requirement(f, t, custom, ladder=["a", "b"])
        # scope_level of f is "a", scope_level of t is "global"
        # so from_level="a", to_level="global" — won't match "a" → "b"
        assert br is None


# =============================================================================
# TestScopeLevel
# =============================================================================


class TestScopeLevel:
    def test_resource_pinned(self):
        s = Scope.from_dict({
            "resource": "host:db12",
            "service": "payments",
            "region": "us-east-1",
        })
        assert s.scope_level() == "resource"

    def test_service_pinned(self):
        s = Scope.from_dict({
            "resource": "*",
            "service": "payments",
            "region": "us-east-1",
        })
        assert s.scope_level() == "service"

    def test_all_wildcard(self):
        s = Scope.from_dict({
            "resource": "*", "service": "*", "region": "*",
            "environment": "*", "tenant": "*",
        })
        assert s.scope_level() == "global"

    def test_custom_ladder(self):
        s = Scope.from_dict({"a": "x", "b": "*"})
        assert s.scope_level(["a", "b", "c"]) == "a"

    def test_no_ladder_axes(self):
        s = Scope.from_dict({"custom_axis": "value"})
        assert s.scope_level() == "custom"

    def test_partial_ladder(self):
        s = Scope.from_dict({
            "resource": "*",
            "service": "*",
            "region": "us-east-1",
        })
        assert s.scope_level() == "region"

    def test_multiple_pinned_returns_most_specific(self):
        """When resource AND service are both pinned, returns resource."""
        s = Scope.from_dict({
            "resource": "host:db12",
            "service": "payments",
            "region": "us-east-1",
            "environment": "prod",
        })
        assert s.scope_level() == "resource"

    def test_time_window_orthogonal(self):
        """time_window is not in spatial ladder — doesn't affect level."""
        s = Scope.from_dict({
            "time_window": "2025-01-01T00:00:00Z/2025-01-01T01:00:00Z",
        })
        assert s.scope_level() == "custom"

    def test_time_window_with_spatial(self):
        """time_window doesn't change spatial level."""
        s = Scope.from_dict({
            "service": "payments",
            "time_window": "2025-01-01T00:00:00Z/2025-01-01T01:00:00Z",
        })
        assert s.scope_level() == "service"

    def test_deterministic_across_calls(self):
        """Same scope always returns same level."""
        s = Scope.from_dict({
            "resource": "*", "service": "payments", "region": "*",
        })
        results = [s.scope_level() for _ in range(100)]
        assert all(r == "service" for r in results)
