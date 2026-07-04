"""Tests for state_index_export.v0 (Slice 0 of GOV_GAP_STATE_REGISTRY_001).

The export makes state legible; it does not make state true. These tests pin the classification
heuristics, provenance tagging, determinism, and divergence warnings against a synthetic fixture
repo (hermetic — not the live corpus).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.state_index_export import (
    SCHEMA,
    SOURCE_NAMESPACE,
    export_records,
    write_export,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A miniature AG-shaped state corpus."""
    r = tmp_path

    # specs/gaps
    (r / "specs" / "gaps").mkdir(parents=True)
    (r / "specs" / "gaps" / "GOV_GAP_EXAMPLE_001.md").write_text(
        "# GOV_GAP_EXAMPLE_001: Example gap\n\n## Status\nProposed (v2)\n\n## Summary\nx\n"
    )

    # docs/playbooks
    (r / "docs" / "playbooks").mkdir(parents=True)
    (r / "docs" / "playbooks" / "governed-playbooks.md").write_text(
        "# Governed Playbooks\n\n> **Status:** design capture\n"
    )
    (r / "docs" / "playbooks" / "slice-3-exit-ticket.md").write_text(
        "# Slice 3 — exit ticket\n\nbody\n"
    )
    (r / "docs" / "playbooks" / "h2-live-run-contract-review.md").write_text(
        "# H2 live run contract review\n"
    )

    # docs/campaigns
    camp = r / "docs" / "campaigns" / "demo-campaign"
    camp.mkdir(parents=True)
    (camp / "CAMPAIGN.md").write_text("# Demo campaign\n")
    (camp / "STATUS.md").write_text("# Status — demo\n\nAs of today.\n")
    (camp / "NEXT.md").write_text("# Next — demo\n\ndo the thing\n")
    (camp / "DECISIONS.md").write_text("# Decisions — demo\n")
    (camp / "GRANTS.yaml").write_text("campaign: demo-campaign\ngrants: []\n")

    # working
    (r / "working").mkdir()
    (r / "working" / "P4_PARKED_2026-06-16.md").write_text("# P4 parked\n")
    (r / "working" / "candidate-thing.md").write_text("# Candidate thing\n")
    (r / "working" / "EXIT_2026-06-23_demo.md").write_text("# Exit demo\n")
    (r / "working" / "random-scratch-note.md").write_text("# Random scratch\n")

    # .governor/backlog (declared)
    (r / ".governor" / "backlog").mkdir(parents=True)
    (r / ".governor" / "backlog" / "do-the-thing.json").write_text(
        json.dumps(
            {
                "id": "do-the-thing",
                "repo": "agent_gov",
                "kind": "build_slice",
                "spec_ref": "specs/gaps/GOV_GAP_EXAMPLE_001.md §3",
                "status": "filed",
                "acceptance": "it works",
            }
        )
    )
    # declared item citing a non-existent spec_ref → divergence warning
    (r / ".governor" / "backlog" / "orphan-ref.json").write_text(
        json.dumps(
            {
                "id": "orphan-ref",
                "kind": "build_slice",
                "spec_ref": "specs/gaps/DOES_NOT_EXIST.md",
                "status": "done",
            }
        )
    )

    # .governor/campaigns (declared)
    (r / ".governor" / "campaigns").mkdir(parents=True)
    (r / ".governor" / "campaigns" / "demo-campaign.yaml").write_text(
        "schema: ag-campaign-manifest/v0\ncampaign: demo-campaign\nnext_build:\n  status: active\n"
    )

    return r


def _by_path(records: list[dict]) -> dict[str, dict]:
    return {r["source_path"]: r for r in records}


def test_gap_classification(repo: Path) -> None:
    recs = _by_path(export_records(repo))
    g = recs["specs/gaps/GOV_GAP_EXAMPLE_001.md"]
    assert g["kind"] == "gap"
    assert g["provenance_class"] == "observed"
    assert g["title"] == "GOV_GAP_EXAMPLE_001: Example gap"
    # "Proposed (v2)" normalises to the project_lifecycle value "planned"
    assert g["status"] == "planned"


def test_playbook_and_review_classification(repo: Path) -> None:
    recs = _by_path(export_records(repo))
    assert recs["docs/playbooks/governed-playbooks.md"]["kind"] == "playbook"
    assert recs["docs/playbooks/slice-3-exit-ticket.md"]["kind"] == "review_gate"
    assert recs["docs/playbooks/h2-live-run-contract-review.md"]["kind"] == "review_gate"
    # inline **Status:** design capture -> triaged
    assert recs["docs/playbooks/governed-playbooks.md"]["status"] == "triaged"


def test_campaign_file_classification(repo: Path) -> None:
    recs = _by_path(export_records(repo))
    assert recs["docs/campaigns/demo-campaign/CAMPAIGN.md"]["kind"] == "work_packet"
    assert recs["docs/campaigns/demo-campaign/STATUS.md"]["kind"] == "work_packet"
    assert recs["docs/campaigns/demo-campaign/NEXT.md"]["kind"] == "planned_slice"
    assert recs["docs/campaigns/demo-campaign/DECISIONS.md"]["kind"] == "operator_decision"
    grants = recs["docs/campaigns/demo-campaign/GRANTS.yaml"]
    assert grants["kind"] == "waiver"
    # GRANTS lives under docs/ → observed, NOT declared
    assert grants["provenance_class"] == "observed"


def test_working_classification(repo: Path) -> None:
    recs = _by_path(export_records(repo))
    assert recs["working/P4_PARKED_2026-06-16.md"]["kind"] == "parked_candidate"
    assert recs["working/candidate-thing.md"]["kind"] == "parked_candidate"
    assert recs["working/EXIT_2026-06-23_demo.md"]["kind"] == "work_packet"
    # ambiguous working note → other + warning
    scratch = recs["working/random-scratch-note.md"]
    assert scratch["kind"] == "other"
    assert any("kind_ambiguous" in w for w in scratch["warnings"])


def test_provenance_class_declared_vs_observed(repo: Path) -> None:
    recs = _by_path(export_records(repo))
    assert recs[".governor/backlog/do-the-thing.json"]["provenance_class"] == "declared"
    assert recs[".governor/campaigns/demo-campaign.yaml"]["provenance_class"] == "declared"
    assert recs["specs/gaps/GOV_GAP_EXAMPLE_001.md"]["provenance_class"] == "observed"
    # execution is NEVER emitted by Slice 0
    assert all(r["provenance_class"] in ("declared", "observed") for r in recs.values())


def test_backlog_item_status_mapping(repo: Path) -> None:
    recs = _by_path(export_records(repo))
    item = recs[".governor/backlog/do-the-thing.json"]
    assert item["kind"] == "backlog_item"
    assert item["id"] == "do-the-thing"
    assert item["status"] == "planned"  # "filed" -> planned


def test_divergence_warning_direction_unattested(repo: Path) -> None:
    recs = _by_path(export_records(repo))
    ok = recs[".governor/backlog/do-the-thing.json"]
    assert not any("spec_ref_unresolved" in w for w in ok["warnings"])
    orphan = recs[".governor/backlog/orphan-ref.json"]
    assert any("spec_ref_unresolved" in w for w in orphan["warnings"])
    assert any("direction unattested" in w for w in orphan["warnings"])


def test_deterministic_ordering(repo: Path) -> None:
    recs = export_records(repo)
    paths = [r["source_path"] for r in recs]
    assert paths == sorted(paths)


def test_stable_source_hashes_and_byte_stable_export(repo: Path) -> None:
    a = export_records(repo)
    b = export_records(repo)
    assert a == b
    for r in a:
        assert r["source_hash"].startswith("sha256:")
    # written file is byte-stable across runs
    p1 = write_export(repo, repo / "out1.json")
    p2 = write_export(repo, repo / "out2.json")
    assert p1.read_bytes() == p2.read_bytes()


def test_record_shape_and_schema_fields(repo: Path) -> None:
    recs = export_records(repo)
    assert recs, "expected at least one record"
    expected_keys = {
        "schema",
        "source_namespace",
        "provenance_class",
        "id",
        "kind",
        "status",
        "title",
        "source_path",
        "source_hash",
        "warnings",
    }
    for r in recs:
        assert set(r.keys()) == expected_keys
        assert r["schema"] == SCHEMA
        assert r["source_namespace"] == SOURCE_NAMESPACE


def test_writes_only_under_target(repo: Path) -> None:
    default = write_export(repo)
    assert default == (repo / ".governor" / "exports" / "state_index_export.v0.json").resolve()
    assert default.exists()
    # source docs untouched — re-scan yields identical hashes
    before = {r["source_path"]: r["source_hash"] for r in export_records(repo)}
    write_export(repo)
    after = {r["source_path"]: r["source_hash"] for r in export_records(repo)}
    assert before == after


def test_malformed_json_becomes_warning_not_crash(repo: Path) -> None:
    (repo / ".governor" / "backlog" / "broken.json").write_text("{ not valid json ")
    recs = _by_path(export_records(repo))
    broken = recs[".governor/backlog/broken.json"]
    assert broken["kind"] == "backlog_item"
    assert any("parse_error" in w for w in broken["warnings"])
