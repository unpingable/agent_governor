# SPDX-License-Identifier: Apache-2.0
"""Read-only portfolio axis projection and custody contradiction checks."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

import governor.portfolio_audit as audit


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def _write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def _fixture_repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "agent_gov"

    _write_json(
        root / ".governor/backlog/nightshift-functional-mvp.json",
        {
            "id": "nightshift-functional-mvp",
            "status": "blocked",
            "open_items": "NS-1 STAGED, awaiting the operator approval act",
            "wake_condition": "operator approval act to admit NS-1",
        },
    )
    nightshift_status = root / "docs/campaigns/nightshift-functional-mvp/STATUS.md"
    nightshift_status.parent.mkdir(parents=True, exist_ok=True)
    nightshift_status.write_text("# Status\n\n## NS-1 FIRST LIVE RUN — DONE\nOperator kept the diff.\n")

    _write_yaml(
        root / ".governor/campaigns/transition-kernel-pickup.yaml",
        {
            "next_build": {
                "id": "slice-1b-AGGrantAdapter-at-activation-office-2",
                "status": "active",
            }
        },
    )
    transition_status = root / "docs/campaigns/transition-kernel-pickup/STATUS.md"
    transition_status.parent.mkdir(parents=True, exist_ok=True)
    transition_status.write_text("Slice 1b is ADOPTED AND VERIFIED on main.\n")

    _write_yaml(
        root / ".governor/campaigns/ag-admit-self-build.yaml",
        {
            "committed": [{"commit": "fb4322d"}, {"commit": "8a76306"}],
            "state": {"unpushed": True},
        },
    )

    session = root / ".governor/sessions/sess_stale"
    _write_json(
        session / "meta.json", {"session_id": "sess_stale", "state": "active"}
    )
    _write_yaml(session / "ledger.yaml", {"authority": {}})
    _write_json(session / "workspace.json", {"active_thread_ids": []})

    conveyor = root / "docs/campaigns/conveyor-dogfood"
    conveyor.mkdir(parents=True, exist_ok=True)
    (conveyor / "STATUS.md").write_text("CD-2 DONE\nCD-4 RUN (as CD-4B)\n")
    for specimen, queue_id in (
        ("cd2-state-index-roadmap-kind", "conveyor-dogfood-cd2"),
        ("cd4-docs-normalize", "conveyor-dogfood-cd4"),
    ):
        _write_json(
            conveyor / "specimens" / specimen / "queue.json",
            {
                "queue_id": queue_id,
                "items": [{"operator_approved": True}],
            },
        )
    cd4 = conveyor / "specimens" / "cd4-docs-normalize"
    (cd4 / "plan.md").write_text(
        'governance_status: approved\napproval_ref: "operator_approved_2026-07-04"\n'
    )
    (cd4 / "operator_approved_2026-07-04").write_text("operator approval witness\n")

    _write_json(
        root / ".governor/loop.json",
        {
            "current_slice": None,
            "acceptance": "No slice ruled NEXT.",
            "blocked_on": "awaiting operator selection of the next slice",
            "next_action": "AWAIT operator selection",
        },
    )

    standing_db = tmp_path / "standing.db"
    connection = sqlite3.connect(standing_db)
    connection.execute(
        "CREATE TABLE grants (id TEXT, state TEXT, expires_at TEXT)"
    )
    connection.execute(
        "INSERT INTO grants VALUES (?, ?, ?)",
        ("grant-expired", "active", "2026-07-05T18:27:01+00:00"),
    )
    connection.commit()
    connection.close()
    return root, standing_db


def test_legacy_status_does_not_imply_any_axis() -> None:
    axes = audit.normalize_state_axes(
        {"status": "queued", "priority_tier": 1, "operator_approved": True}
    )
    assert set(axes) == set(audit.AXES)
    assert {axis["state"] for axis in axes.values()} == {"unknown"}


def test_explicit_axes_remain_independent() -> None:
    axes = audit.normalize_state_axes(
        {
            "state_axes": {
                "admission": "ratified",
                "selection": "unselected",
                "plan_approval": "none_attached_to_selection",
                "runtime_activity": "inactive",
                "effect_authority": "not_determined",
                "custody": "partial",
            },
            "basis": "campaign receipts",
            "evidence": ["STATUS.md"],
        }
    )
    assert axes["admission"]["state"] == "ratified"
    assert axes["selection"]["state"] == "unselected"
    assert axes["effect_authority"]["state"] == "not_determined"
    assert axes["custody"]["state"] == "partial"
    assert axes["selection"]["basis"] == "campaign receipts"
    assert axes["selection"]["evidence"] == ["STATUS.md"]


def test_nested_axis_can_carry_axis_specific_receipts() -> None:
    axes = audit.normalize_state_axes(
        {
            "state_axes": {
                "selection": {
                    "state": "unselected",
                    "basis": "loop program counter",
                    "evidence": [".governor/loop.json"],
                }
            }
        }
    )
    assert axes["selection"] == {
        "state": "unselected",
        "basis": "loop program counter",
        "evidence": [".governor/loop.json"],
    }
    assert axes["admission"]["state"] == "unknown"


def test_nested_current_disposition_is_the_current_axis_projection() -> None:
    axes = audit.normalize_state_axes(
        {
            "status": "blocked",
            "current_disposition": {
                "schema": audit.DISPOSITION_SCHEMA,
                "state_axes": {
                    "admission": "ratified",
                    "selection": "unselected",
                    "plan_approval": "none_attached_to_selection",
                    "runtime_activity": "inactive",
                    "effect_authority": "not_evidenced_for_unselected_work",
                    "custody": "partial",
                },
                "evidence": ["terminal receipt"],
            },
        }
    )
    assert axes["admission"]["state"] == "ratified"
    assert axes["selection"]["state"] == "unselected"
    assert axes["custody"]["state"] == "partial"
    assert axes["custody"]["evidence"] == ["terminal receipt"]


def test_checker_finds_all_bounded_stale_surfaces(tmp_path: Path, monkeypatch) -> None:
    root, standing_db = _fixture_repo(tmp_path)
    monkeypatch.setattr(audit, "_git_campaign_commits_contained", lambda _root, _commits: True)

    findings = audit.collect_consistency_findings(
        root,
        standing_db=standing_db,
        now=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    codes = [finding.code for finding in findings]

    assert "nightshift_ns1_stale_backlog" in codes
    assert "transition_slice_1b_stale_active" in codes
    assert "ag_admit_stale_unpushed" in codes
    assert "session_stale_active_marker" in codes
    assert "standing_expired_materialized_active" in codes
    assert codes.count("completed_queue_latch_without_disposition") == 2
    assert "completed_plan_approval_without_disposition" in codes
    assert "loop_operator_selection_basis_missing" in codes


def test_append_only_dispositions_retire_queue_latches_without_rewriting_history(
    tmp_path: Path, monkeypatch
) -> None:
    root, standing_db = _fixture_repo(tmp_path)
    monkeypatch.setattr(audit, "_git_campaign_commits_contained", lambda _root, _commits: True)
    conveyor = root / "docs/campaigns/conveyor-dogfood/specimens"

    for specimen in ("cd2-state-index-roadmap-kind", "cd4-docs-normalize"):
        queue_path = conveyor / specimen / "queue.json"
        subjects = [
            {
                "path": queue_path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
            }
        ]
        if specimen == "cd4-docs-normalize":
            for name in ("plan.md", "operator_approved_2026-07-04"):
                artifact = queue_path.parent / name
                subjects.append(
                    {
                        "path": artifact.relative_to(root).as_posix(),
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                )
        _write_json(
            queue_path.parent / "current_disposition.json",
            {
                "schema": audit.DISPOSITION_SCHEMA,
                "subject": {"artifacts": subjects},
                "state_axes": {
                    "admission": "admitted",
                    "selection": "unselected",
                    "plan_approval": "approved_record_retained",
                    "runtime_activity": "terminal",
                    "effect_authority": "terminal_no_live_grant_evidenced",
                    "custody": "complete",
                },
                "basis": "terminal run and promotion receipts",
                "evidence": ["STATUS.md"],
            },
        )

    findings = audit.collect_consistency_findings(
        root,
        standing_db=standing_db,
        now=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    queue_findings = [
        finding for finding in findings
        if finding.code in {
            "completed_queue_latch_without_disposition",
            "completed_plan_approval_without_disposition",
        }
    ]
    assert queue_findings == []
    # The historical approval bits are preserved byte-for-byte as records.
    assert all(
        json.loads((conveyor / specimen / "queue.json").read_text())["items"][0][
            "operator_approved"
        ]
        is True
        for specimen in ("cd2-state-index-roadmap-kind", "cd4-docs-normalize")
    )


def test_explicit_loop_inconsistency_is_reported_not_semantically_resolved(
    tmp_path: Path, monkeypatch
) -> None:
    root, _standing_db = _fixture_repo(tmp_path)
    monkeypatch.setattr(audit, "_git_campaign_commits_contained", lambda _root, _commits: False)
    loop_path = root / ".governor/loop.json"
    loop = json.loads(loop_path.read_text())
    loop["selection_condition"] = {
        "state": "inconsistent_unproven_operator_requirement",
        "claim": "requires_operator",
        "evidence": [],
    }
    _write_json(loop_path, loop)

    findings = audit.collect_consistency_findings(root)
    loop_findings = [finding for finding in findings if finding.code.startswith("loop_")]

    assert [finding.code for finding in loop_findings] == [
        "loop_operator_selection_basis_unresolved"
    ]
    assert loop_findings[0].severity == "unresolved_semantic"


def test_build_audit_projects_six_axes_and_findings(tmp_path: Path, monkeypatch) -> None:
    root, standing_db = _fixture_repo(tmp_path)
    monkeypatch.setattr(audit, "_git_campaign_commits_contained", lambda _root, _commits: True)
    result = audit.build_audit(
        root,
        standing_db=standing_db,
        now=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )

    assert result["schema"] == audit.AUDIT_SCHEMA
    assert set(result["axis_summary"]) == set(audit.AXES)
    backlog = next(record for record in result["records"] if record["id"] == "nightshift-functional-mvp")
    assert backlog["legacy_status"] == "blocked"
    assert backlog["state_axes"]["selection"]["state"] == "unknown"
    assert result["consistency_findings"]


def test_append_only_successors_suppress_superseded_campaign_and_session_claims(
    tmp_path: Path, monkeypatch
) -> None:
    root, _standing_db = _fixture_repo(tmp_path)
    monkeypatch.setattr(audit, "_git_campaign_commits_contained", lambda _root, _commits: True)

    transition_path = root / ".governor/campaigns/transition-kernel-pickup.yaml"
    transition = yaml.safe_load(transition_path.read_text())
    transition["current_disposition"] = {
        "schema": audit.DISPOSITION_SCHEMA,
        "slice_1b": {"status": "completed"},
        "state_axes": {"custody": "partial"},
    }
    _write_yaml(transition_path, transition)

    admit_path = root / ".governor/campaigns/ag-admit-self-build.yaml"
    admit = yaml.safe_load(admit_path.read_text())
    admit["current_disposition"] = {
        "schema": audit.DISPOSITION_SCHEMA,
        "push_state": {"unpushed": False},
        "state_axes": {"custody": "complete"},
    }
    _write_yaml(admit_path, admit)

    _write_json(
        root / "working/current-dispositions/session-sess_stale.json",
        {
            "schema": audit.DISPOSITION_SCHEMA,
            "subject": {"path": ".governor/sessions/sess_stale/meta.json"},
            "state_axes": {
                "runtime_activity": "not_evidenced",
                "effect_authority": "none_recorded",
                "custody": "stale_marker",
            },
        },
    )

    findings = audit.collect_consistency_findings(root)
    codes = {finding.code for finding in findings}
    assert "transition_slice_1b_stale_active" not in codes
    assert "ag_admit_stale_unpushed" not in codes
    assert "session_stale_active_marker" not in codes
