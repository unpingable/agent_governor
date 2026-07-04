# SPDX-License-Identifier: Apache-2.0
"""ReviewPacket schema + serializer (Slice B-11.S3).

A ReviewPacket is evidence, not authority. These tests pin: it stays inert,
operator review defaults required, ``used <= granted`` is structural, and
serialization is deterministic and round-trips. The packet has no method that
runs a command, inspects git, or applies a patch — there is nothing to test there
because there is nothing there.
"""

from __future__ import annotations

import pytest

from governor.playbooks.review_packet import (
    SCHEMA_VERSION,
    STATUS_PROPOSED_PATCH,
    TEST_PASSED,
    AuthoritySet,
    ReviewArtifact,
    ReviewAuthority,
    ReviewFollowup,
    ReviewPacket,
    ReviewTestResult,
)


def _minimal(**overrides) -> ReviewPacket:
    base = dict(
        packet_id="B-11.S3-2026-06-29-a",
        playbook_id="synthetic-cage-verdict",
        repo="ag",
        branch="feat/playbooks-synthetic-conveyor",
        base_branch="feat/playbooks-gov-loop",
        base_sha="515afb0",
        status=STATUS_PROPOSED_PATCH,
    )
    base.update(overrides)
    return ReviewPacket(**base)


# --------------------------------------------------------------------------- #
# Construction + defaults.
# --------------------------------------------------------------------------- #


class TestConstruction:
    def test_minimal_packet_succeeds(self):
        p = _minimal()
        assert p.packet_id == "B-11.S3-2026-06-29-a"
        assert p.schema_version == SCHEMA_VERSION

    def test_operator_review_required_defaults_true(self):
        assert _minimal().operator_review_required is True

    def test_unknown_status_refused(self):
        with pytest.raises(ValueError):
            _minimal(status="merged")  # not in the closed status set

    def test_unknown_test_status_refused(self):
        with pytest.raises(ValueError):
            ReviewTestResult(command="pytest", status="greenish")


# --------------------------------------------------------------------------- #
# Authority invariant: used <= granted (structural).
# --------------------------------------------------------------------------- #


class TestAuthorityInvariant:
    def test_used_push_without_granted_push_raises(self):
        with pytest.raises(ValueError):
            ReviewAuthority(
                granted=AuthoritySet(push=False),
                used=AuthoritySet(push=True),
            )

    def test_used_network_without_granted_network_raises(self):
        with pytest.raises(ValueError):
            ReviewAuthority(
                granted=AuthoritySet(network=False),
                used=AuthoritySet(network=True),
            )

    def test_used_subprocess_without_granted_subprocess_raises(self):
        with pytest.raises(ValueError):
            ReviewAuthority(
                granted=AuthoritySet(subprocess=False),
                used=AuthoritySet(subprocess=True),
            )

    def test_requested_may_exceed_granted(self):
        # asking for more than you get is fine.
        auth = ReviewAuthority(
            requested=AuthoritySet(commit=True, push=True, network=True),
            granted=AuthoritySet(commit=True),
            used=AuthoritySet(commit=True),
        )
        assert auth.granted.commit is True

    def test_granted_may_exceed_used(self):
        auth = ReviewAuthority(
            granted=AuthoritySet(commit=True, network=True),
            used=AuthoritySet(commit=True),
        )
        assert auth.used.network is False


# --------------------------------------------------------------------------- #
# Deterministic serialization + round trip.
# --------------------------------------------------------------------------- #


class TestSerialization:
    def test_manifest_is_deterministic(self):
        p = _minimal(
            files_changed=("src/a.py", "tests/test_a.py"),
            risks=("a risk",),
        )
        assert p.to_json() == p.to_json()

    def test_manifest_includes_core_fields(self):
        p = _minimal(
            explicit_non_actions=("did not push", "did not run live origin"),
        )
        d = p.to_manifest_dict()
        assert d["schema_version"] == SCHEMA_VERSION
        assert set(d["authority"].keys()) == {"requested", "granted", "used"}
        assert d["explicit_non_actions"] == ["did not push", "did not run live origin"]
        assert d["operator_review_required"] is True

    def test_json_round_trip_preserves_contents(self):
        p = _minimal(
            proposed_head_sha="deadbeef",
            lane="synthetic",
            files_changed=("src/governor/playbooks/sandbox_cage.py",),
            tests=(ReviewTestResult(command="pytest tests/playbooks -q", status=TEST_PASSED, exit_code=0),),
            artifacts=(ReviewArtifact(kind="diff", path="changes.patch", sha256="abc"),),
            risks=("lanes must stay disjoint",),
            design_notes=("safe!=live by construction",),
            explicit_non_actions=("no push",),
            followups=(ReviewFollowup(id="S4", title="queue parser", reason="feed the conveyor", suggested_next_gate="B-11.S4"),),
            authority=ReviewAuthority(
                requested=AuthoritySet(commit=True, push=True),
                granted=AuthoritySet(commit=True),
                used=AuthoritySet(commit=True),
            ),
        )
        restored = ReviewPacket.from_json(p.to_json())
        assert restored == p

    def test_round_trip_rebuilds_tuples_not_lists(self):
        p = _minimal(files_changed=("a", "b"))
        restored = ReviewPacket.from_manifest_dict(p.to_manifest_dict())
        assert isinstance(restored.files_changed, tuple)


# --------------------------------------------------------------------------- #
# Markdown summary.
# --------------------------------------------------------------------------- #


class TestMarkdownSummary:
    def test_summary_includes_required_sections(self):
        p = _minimal(
            files_changed=("src/x.py",),
            tests=(ReviewTestResult(command="pytest", status=TEST_PASSED),),
            risks=("a risk worth noting",),
            explicit_non_actions=("did not push",),
            followups=(ReviewFollowup(id="S4", title="next", reason="because"),),
        )
        md = p.to_markdown_summary()
        assert p.packet_id in md
        assert p.playbook_id in md
        assert p.branch in md
        assert p.base_sha in md
        assert p.status in md
        assert "pytest" in md
        assert "a risk worth noting" in md
        assert "did not push" in md
        assert "REQUIRED" in md  # operator review required


# --------------------------------------------------------------------------- #
# Follow-ups + artifacts are inert references / suggestions.
# --------------------------------------------------------------------------- #


class TestInertReferences:
    def test_followups_serialize_as_suggestions_only(self):
        f = ReviewFollowup(id="S4", title="queue parser", reason="feed the conveyor")
        d = f.as_dict()
        # A suggestion has no execution / approval fields.
        assert set(d.keys()) == {"id", "title", "reason", "suggested_next_gate"}
        assert "approved" not in d
        assert "execute" not in d

    def test_artifacts_serialize_as_references_only(self):
        a = ReviewArtifact(kind="diff", path="changes.patch")
        d = a.as_dict()
        assert set(d.keys()) == {"kind", "path", "sha256", "description"}
        # No content / no apply field — the packet never carries trusted bytes.
        assert "content" not in d
        assert "apply" not in d


# --------------------------------------------------------------------------- #
# Optional file map: relative safe names, strings only.
# --------------------------------------------------------------------------- #


class TestFileMap:
    def test_file_map_emits_relative_safe_strings(self):
        fm = _minimal(risks=("r",)).to_file_map()
        assert "manifest.json" in fm
        assert "summary.md" in fm
        for name, content in fm.items():
            assert not name.startswith("/")  # relative only
            assert ".." not in name  # no traversal
            assert isinstance(content, str)
