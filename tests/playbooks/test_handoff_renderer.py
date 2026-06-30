# SPDX-License-Identifier: Apache-2.0
"""Tests for the S6 handoff renderer (QueuedPlaybook → sealed actor handoff)."""

from __future__ import annotations

import json

import pytest

from governor.playbooks.handoff_renderer import (
    ACTOR_CLAUDE,
    ACTOR_CODEX,
    CODE_AUTHORITY_NOT_CLOSED,
    CODE_OPERATOR_APPROVAL_MISSING,
    CODE_OUTPUT_KIND_NOT_REVIEW_PACKET,
    CODE_UNKNOWN_ACTOR_KIND,
    CODE_UNSUPPORTED_QUEUE_MODE,
    CODE_UNSUPPORTED_SCHEMA,
    EXPECTED_OUTPUT_KIND,
    PROHIBITED_AUTHORITY,
    HandoffPacket,
    HandoffRenderError,
    HandoffSealError,
    render_handoff,
    render_queue_handoffs,
)
from governor.playbooks.playbook_queue import (
    OUTPUT_REVIEW_PACKET,
    QUEUE_AUTHORITY_KEYS,
    PlaybookQueue,
    QueuedPlaybook,
    QueuedPlaybookAuthority,
)
from governor.playbooks.review_packet import SCHEMA_VERSION as RP_SCHEMA


def _item(playbook_id: str = "pb-1", **over) -> QueuedPlaybook:
    kw = dict(
        playbook_id=playbook_id,
        title="Tidy the widget",
        objective="Refactor the widget for clarity; no behavior change.",
        output_kind=OUTPUT_REVIEW_PACKET,
        allowed_paths=("src/widget/",),
        forbidden_paths=("src/secret/",),
        required_tests=("pytest tests/widget -q",),
        stop_conditions=("any test fails", "scope exceeded"),
        operator_approved=True,
        lane="feat/widget",
        base_branch="main",
        base_sha="deadbeef",
    )
    kw.update(over)
    return QueuedPlaybook(**kw)


def _queue(*items: QueuedPlaybook) -> PlaybookQueue:
    return PlaybookQueue(
        queue_id="q-1",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        mode="synthetic_conveyor",
        items=items or (_item(),),
    )


def _render(item=None, actor=ACTOR_CLAUDE) -> HandoffPacket:
    return render_handoff(
        item or _item(),
        handoff_id="h-1",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        actor_kind=actor,
    )


# --------------------------------------------------------------------------- #
# Happy path + field carry.
# --------------------------------------------------------------------------- #


def test_render_carries_scope_and_context():
    h = _render()
    assert h.playbook_id == "pb-1"
    assert h.actor_kind == ACTOR_CLAUDE
    assert h.objective.startswith("Refactor")
    assert h.allowed_paths == ("src/widget/",)
    assert h.forbidden_paths == ("src/secret/",)
    assert h.required_tests == ("pytest tests/widget -q",)
    assert h.stop_conditions == ("any test fails", "scope exceeded")


def test_both_actor_kinds_render():
    for actor in (ACTOR_CLAUDE, ACTOR_CODEX):
        assert _render(actor=actor).actor_kind == actor


def test_item_base_and_lane_override_queue_context():
    h = _render(_item(base_branch="release", base_sha="1234", lane="feat/x"))
    assert h.base_branch == "release"
    assert h.base_sha == "1234"
    assert h.lane == "feat/x"


def test_item_falls_back_to_queue_context_when_unset():
    item = _item(base_branch=None, base_sha=None, lane=None)
    h = render_handoff(
        item,
        handoff_id="h-1",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        actor_kind=ACTOR_CLAUDE,
    )
    assert h.base_branch == "main"
    assert h.base_sha == "cafef00d"
    assert h.lane is None


# --------------------------------------------------------------------------- #
# Authority is prohibited, not negotiable.
# --------------------------------------------------------------------------- #


def test_prohibited_authority_is_the_full_axis_set():
    assert set(PROHIBITED_AUTHORITY) == set(QUEUE_AUTHORITY_KEYS)
    assert list(PROHIBITED_AUTHORITY) == sorted(PROHIBITED_AUTHORITY)


def test_manifest_prohibits_all_axes_and_has_no_permit_surface():
    m = _render().to_manifest_dict()
    assert m["prohibited_authority"] == list(PROHIBITED_AUTHORITY)
    assert m["expected_output_kind"] == EXPECTED_OUTPUT_KIND == OUTPUT_REVIEW_PACKET
    assert m["expected_output_schema"] == RP_SCHEMA
    # No key anywhere grants/permits authority.
    blob = json.dumps(m).lower()
    assert "granted" not in blob and "permit" not in blob


# --------------------------------------------------------------------------- #
# Sealing.
# --------------------------------------------------------------------------- #


def test_seal_is_deterministic_and_prefixed():
    a, b = _render(), _render()
    assert a.compute_seal() == b.compute_seal()
    assert a.compute_seal().startswith("sha256:")


def test_seal_changes_when_body_changes():
    base = _render().compute_seal()
    assert _render(_item(objective="different objective entirely")).compute_seal() != base
    assert _render(actor=ACTOR_CODEX).compute_seal() != base


def test_json_round_trip_preserves_seal_and_fields():
    h = _render()
    rt = HandoffPacket.from_json(h.to_json())
    assert rt.to_manifest_dict() == h.to_manifest_dict()
    assert rt.compute_seal() == h.compute_seal()


def test_tampered_seal_is_refused():
    m = _render().to_manifest_dict()
    m["objective"] = "smuggled different objective"  # body changed, seal stale
    with pytest.raises(HandoffSealError):
        HandoffPacket.from_manifest_dict(m)


def test_missing_seal_is_accepted_and_recomputed():
    m = _render().to_manifest_dict()
    del m["seal"]
    rebuilt = HandoffPacket.from_manifest_dict(m)
    assert rebuilt.compute_seal() == _render().compute_seal()


def test_verify_seal():
    h = _render()
    assert h.verify_seal(h.compute_seal())
    assert not h.verify_seal("sha256:0")


def test_to_json_is_stable():
    h = _render()
    assert h.to_json() == h.to_json()


# --------------------------------------------------------------------------- #
# Construction + render-time refusals (closed codes).
# --------------------------------------------------------------------------- #


def test_unknown_actor_kind_refused_at_render():
    with pytest.raises(HandoffRenderError) as ei:
        _render(actor="gpt5")
    assert ei.value.code == CODE_UNKNOWN_ACTOR_KIND


def test_unknown_actor_kind_refused_at_construction():
    with pytest.raises(HandoffRenderError) as ei:
        HandoffPacket(
            handoff_id="h",
            playbook_id="p",
            actor_kind="gpt5",
            repo="r",
            base_branch="main",
            base_sha="x",
            objective="o",
            title="t",
            allowed_paths=("a/",),
            stop_conditions=("s",),
        )
    assert ei.value.code == CODE_UNKNOWN_ACTOR_KIND


def test_unsupported_schema_refused_at_construction():
    with pytest.raises(HandoffRenderError) as ei:
        HandoffPacket(
            handoff_id="h",
            playbook_id="p",
            actor_kind=ACTOR_CLAUDE,
            repo="r",
            base_branch="main",
            base_sha="x",
            objective="o",
            title="t",
            allowed_paths=("a/",),
            stop_conditions=("s",),
            schema_version="handoff.v999",
        )
    assert ei.value.code == CODE_UNSUPPORTED_SCHEMA


def test_render_re_asserts_approval_defense_in_depth():
    item = _item()
    object.__setattr__(item, "operator_approved", False)  # bypass item construction
    with pytest.raises(HandoffRenderError) as ei:
        _render(item)
    assert ei.value.code == CODE_OPERATOR_APPROVAL_MISSING


def test_render_re_asserts_closed_authority_defense_in_depth():
    item = _item()
    object.__setattr__(item, "authority", QueuedPlaybookAuthority(commit=True))
    with pytest.raises(HandoffRenderError) as ei:
        _render(item)
    assert ei.value.code == CODE_AUTHORITY_NOT_CLOSED


def test_render_re_asserts_output_kind_defense_in_depth():
    item = _item()
    object.__setattr__(item, "output_kind", "merge")
    with pytest.raises(HandoffRenderError) as ei:
        _render(item)
    assert ei.value.code == CODE_OUTPUT_KIND_NOT_REVIEW_PACKET


# --------------------------------------------------------------------------- #
# Queue-level rendering.
# --------------------------------------------------------------------------- #


def test_render_queue_handoffs_maps_items_with_derived_ids():
    # Items without item-level base → fall back to queue context.
    a = _item("pb-a", base_branch=None, base_sha=None)
    b = _item("pb-b", base_branch=None, base_sha=None)
    q = _queue(a, b)
    hs = render_queue_handoffs(q, actor_kind=ACTOR_CODEX)
    assert [h.handoff_id for h in hs] == ["handoff-q-1-pb-a", "handoff-q-1-pb-b"]
    assert all(h.repo == "agent_gov" and h.base_sha == "cafef00d" for h in hs)
    assert all(h.actor_kind == ACTOR_CODEX for h in hs)


def test_render_queue_refuses_non_synthetic_mode():
    q = _queue()
    object.__setattr__(q, "mode", "live")  # bypass queue construction
    with pytest.raises(HandoffRenderError) as ei:
        render_queue_handoffs(q, actor_kind=ACTOR_CLAUDE)
    assert ei.value.code == CODE_UNSUPPORTED_QUEUE_MODE


# --------------------------------------------------------------------------- #
# File map + prompt are inert strings.
# --------------------------------------------------------------------------- #


def test_file_map_returns_strings_only():
    fm = _render().to_file_map()
    assert set(fm) == {"handoff.json", "PROMPT.md"}
    assert all(isinstance(v, str) for v in fm.values())
    assert json.loads(fm["handoff.json"])["handoff_id"] == "h-1"


def test_prompt_states_prohibitions_scope_and_evidence_posture():
    p = _render().to_prompt_markdown()
    for axis in PROHIBITED_AUTHORITY:
        assert f"MUST NOT {axis}" in p
    assert "src/widget/" in p
    assert "Refactor" in p
    assert "evidence, not authority" in p
    assert EXPECTED_OUTPUT_KIND in p


def test_prompt_addressee_differs_by_actor():
    assert "Claude Code" in _render(actor=ACTOR_CLAUDE).to_prompt_markdown()
    assert "Codex" in _render(actor=ACTOR_CODEX).to_prompt_markdown()
