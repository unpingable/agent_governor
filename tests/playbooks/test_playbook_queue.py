# SPDX-License-Identifier: Apache-2.0
"""Overnight playbook queue parser (Slice B-11.S4).

A queue item is permission to ATTEMPT bounded offline work later — never to merge,
push, recurse, or expand authority. These tests pin the fail-closed gates: explicit
per-item operator approval, fully-closed authority, review_packet output, synthetic
mode, safe static paths, inert test/stop-condition strings, deterministic
serialization. The parser never runs anything.
"""

from __future__ import annotations

import pytest

from governor.playbooks.playbook_queue import (
    MODE_SYNTHETIC_CONVEYOR,
    OUTPUT_REVIEW_PACKET,
    SOURCE_REVIEWPACKET_FOLLOWUP,
    PlaybookQueue,
    QueuedPlaybook,
    QueuedPlaybookAuthority,
    QueueItemSource,
    QueueValidationError,
)


def _item(**overrides) -> dict:
    base = dict(
        playbook_id="B-11.S5-validator",
        title="ReviewPacket-vs-queue validator",
        objective="static authority/path validation",
        lane="synthetic",
        authority={},  # all closed by default
        allowed_paths=["src/governor/playbooks/**", "tests/playbooks/**"],
        forbidden_paths=["src/governor/doctrine/**", ".github/**"],
        required_tests=["pytest tests/playbooks -q"],
        stop_conditions=["requires subprocess", "requires network"],
        output_kind=OUTPUT_REVIEW_PACKET,
        operator_approved=True,
        source={"kind": "operator_seeded"},
    )
    base.update(overrides)
    return base


def _queue(**overrides) -> dict:
    base = dict(
        schema_version=1,
        queue_id="night-2026-06-29-a",
        repo="ag",
        base_branch="feat/playbooks-synthetic-conveyor",
        base_sha="0d32639",
        mode=MODE_SYNTHETIC_CONVEYOR,
        items=[_item()],
    )
    base.update(overrides)
    return base


def _parse(**overrides) -> PlaybookQueue:
    return PlaybookQueue.from_manifest_dict(_queue(**overrides))


# --------------------------------------------------------------------------- #
# Minimal valid queue + serialization.
# --------------------------------------------------------------------------- #


class TestValidQueue:
    def test_minimal_valid_queue_parses(self):
        q = _parse()
        assert q.mode == MODE_SYNTHETIC_CONVEYOR
        assert len(q.items) == 1
        assert q.items[0].operator_approved is True

    def test_item_order_preserved(self):
        q = _parse(
            items=[
                _item(playbook_id="a"),
                _item(playbook_id="b"),
                _item(playbook_id="c"),
            ]
        )
        assert [it.playbook_id for it in q.items] == ["a", "b", "c"]

    def test_serialization_deterministic(self):
        q = _parse()
        assert q.to_json() == q.to_json()

    def test_json_round_trip(self):
        q = _parse()
        assert PlaybookQueue.from_json(q.to_json()) == q


# --------------------------------------------------------------------------- #
# Explicit operator approval — the anti-recursion latch.
# --------------------------------------------------------------------------- #


class TestOperatorApproval:
    def test_missing_operator_approved_rejected(self):
        item = _item()
        del item["operator_approved"]
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[item])
        assert e.value.code == "not_operator_approved"

    def test_operator_approved_false_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(operator_approved=False)])
        assert e.value.code == "not_operator_approved"

    def test_followup_without_approval_rejected(self):
        item = _item(
            source={"kind": SOURCE_REVIEWPACKET_FOLLOWUP, "packet_id": "B-11.S3-x"},
            operator_approved=False,
        )
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[item])
        assert e.value.code == "not_operator_approved"

    def test_followup_with_explicit_approval_parses_but_inert(self):
        item = _item(
            source={"kind": SOURCE_REVIEWPACKET_FOLLOWUP, "packet_id": "B-11.S3-x"},
            operator_approved=True,
        )
        q = _parse(items=[item])
        it = q.items[0]
        assert it.operator_approved is True
        assert it.source.kind == SOURCE_REVIEWPACKET_FOLLOWUP
        # Provenance is recorded; it confers no execution — it is just data.
        assert it.source.packet_id == "B-11.S3-x"


# --------------------------------------------------------------------------- #
# Authority is fully closed for the synthetic conveyor.
# --------------------------------------------------------------------------- #


class TestAuthorityClosed:
    @pytest.mark.parametrize(
        "axis",
        [
            "commit",
            "push",
            "network",
            "subprocess",
            "live_origin",
            "real_cage_backend",
            "doctrine_write",
            "constellation_write",
        ],
    )
    def test_any_open_authority_axis_rejected(self, axis):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(authority={axis: True})])
        assert e.value.code == "authority_not_closed"

    def test_all_closed_authority_accepted(self):
        q = _parse(items=[_item(authority={})])
        assert q.items[0].authority == QueuedPlaybookAuthority()


# --------------------------------------------------------------------------- #
# Output kind + mode.
# --------------------------------------------------------------------------- #


class TestOutputKindAndMode:
    def test_review_packet_output_accepted(self):
        assert _parse().items[0].output_kind == OUTPUT_REVIEW_PACKET

    @pytest.mark.parametrize(
        "bad", ["merge", "push", "commit", "doctrine_update", "live_admission"]
    )
    def test_non_review_packet_output_rejected(self, bad):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(output_kind=bad)])
        assert e.value.code == "unsupported_output_kind"

    @pytest.mark.parametrize("bad", ["live", "autopilot", "batch_autonomous"])
    def test_non_synthetic_mode_rejected(self, bad):
        with pytest.raises(QueueValidationError) as e:
            _parse(mode=bad)
        assert e.value.code == "unsupported_mode"


# --------------------------------------------------------------------------- #
# Duplicate ids + schema.
# --------------------------------------------------------------------------- #


class TestStructure:
    def test_duplicate_playbook_id_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(playbook_id="dup"), _item(playbook_id="dup")])
        assert e.value.code == "duplicate_playbook_id"

    def test_unsupported_schema_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(schema_version=99)
        assert e.value.code == "unsupported_schema"

    def test_unknown_source_kind_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(source={"kind": "self_authorized"})])
        assert e.value.code == "unknown_source_kind"


# --------------------------------------------------------------------------- #
# Path validation — static, no filesystem touch.
# --------------------------------------------------------------------------- #


class TestPathValidation:
    def test_relative_globs_accepted(self):
        q = _parse(items=[_item(allowed_paths=["src/governor/playbooks/**"])])
        assert q.items[0].allowed_paths == ("src/governor/playbooks/**",)

    @pytest.mark.parametrize(
        "bad", ["/etc/passwd", "..", "../escape", "a/../../b", ".", ""]
    )
    def test_unsafe_allowed_path_rejected(self, bad):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(allowed_paths=[bad])])
        assert e.value.code in {"unsafe_path", "empty_allowed_paths"}

    def test_empty_allowed_paths_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(allowed_paths=[])])
        assert e.value.code == "empty_allowed_paths"

    def test_unsafe_forbidden_path_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(forbidden_paths=["../outside"])])
        assert e.value.code == "unsafe_path"

    def test_path_order_preserved_and_not_expanded(self):
        paths = ["src/governor/playbooks/**", "tests/playbooks/**", "docs/playbooks/**"]
        q = _parse(items=[_item(allowed_paths=paths)])
        assert list(q.items[0].allowed_paths) == paths


# --------------------------------------------------------------------------- #
# Required tests + stop conditions are inert declarations.
# --------------------------------------------------------------------------- #


class TestInertDeclarations:
    def test_required_tests_preserved(self):
        tests = ["pytest tests/playbooks -q", "ruff check src/governor/playbooks"]
        q = _parse(items=[_item(required_tests=tests)])
        assert list(q.items[0].required_tests) == tests

    def test_empty_test_command_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(required_tests=["pytest", "  "])])
        assert e.value.code == "empty_test_command"

    def test_missing_stop_conditions_rejected(self):
        item = _item()
        del item["stop_conditions"]
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[item])
        assert e.value.code in {"empty_stop_conditions", "missing_required_field"}

    def test_empty_stop_conditions_rejected(self):
        with pytest.raises(QueueValidationError) as e:
            _parse(items=[_item(stop_conditions=[])])
        assert e.value.code == "empty_stop_conditions"


# --------------------------------------------------------------------------- #
# Inertness: the parser introduces no execution surface.
# --------------------------------------------------------------------------- #


class TestInertness:
    def test_no_execution_methods_on_queue(self):
        q = _parse()
        for forbidden in ("run", "execute", "schedule", "apply", "dispatch"):
            assert not hasattr(q, forbidden)

    def test_no_execution_methods_on_item(self):
        it = _parse().items[0]
        for forbidden in ("run", "execute", "apply", "dispatch"):
            assert not hasattr(it, forbidden)
