# SPDX-License-Identifier: Apache-2.0
"""Read-only portfolio state projection and custody consistency checks.

This module deliberately keeps six independent axes.  In particular, a
backlog status such as ``queued`` is *not* evidence that work is selected,
approved, running, or effect-authorized.  Axis values are projected only from
an explicit ``state_axes`` object; absent values remain ``unknown``.

The consistency checks are narrow comparisons over already-recorded state.
They do not repair state and do not adjudicate authority.
"""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


AUDIT_SCHEMA = "ag-portfolio-audit/v1"
DISPOSITION_SCHEMA = "ag-current-disposition/v1"
AXES = (
    "admission",
    "selection",
    "plan_approval",
    "runtime_activity",
    "effect_authority",
    "custody",
)


@dataclass(frozen=True)
class ConsistencyFinding:
    """One evidence-backed contradiction or unresolved state seam."""

    code: str
    severity: str
    subject: str
    claim: str
    ground_truth: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "subject": self.subject,
            "claim": self.claim,
            "ground_truth": self.ground_truth,
            "evidence": list(self.evidence),
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_yaml(path: Path) -> dict[str, Any] | None:
    try:
        value = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return None
    return value if isinstance(value, dict) else None


def _read_text(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def load_backlog(root: Path) -> list[dict[str, Any]]:
    """Load declared backlog records in deterministic path order."""

    records: list[dict[str, Any]] = []
    for path in sorted((root / ".governor" / "backlog").glob("*.json")):
        record = _read_json(path)
        if record is None:
            continue
        record = dict(record)
        record["_source_path"] = path.relative_to(root).as_posix()
        records.append(record)
    return records


def normalize_state_axes(record: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return all six axes without deriving authority from legacy fields.

    Both compact values (``{"selection": "unselected"}``) and nested values
    (``{"selection": {"state": "unselected", ...}}``) are accepted.  A
    record-wide basis/evidence is carried onto explicit compact values.  A
    missing or malformed value is ``unknown``.
    """

    record = record or {}
    # Append-only successors are deliberately nested so the historical claim
    # remains intact.  The successor is the current projection when present.
    disposition = record.get("current_disposition")
    axis_source = (
        disposition
        if not isinstance(record.get("state_axes"), dict)
        and isinstance(disposition, dict)
        and isinstance(disposition.get("state_axes"), dict)
        else record
    )
    raw_axes = axis_source.get("state_axes")
    if not isinstance(raw_axes, dict):
        raw_axes = {}
    record_basis = axis_source.get("basis")
    record_evidence = axis_source.get("evidence")
    if not isinstance(record_evidence, list):
        record_evidence = []

    normalized: dict[str, dict[str, Any]] = {}
    for axis in AXES:
        raw = raw_axes.get(axis)
        if isinstance(raw, str) and raw:
            normalized[axis] = {
                "state": raw,
                "basis": record_basis,
                "evidence": list(record_evidence),
            }
        elif isinstance(raw, dict) and isinstance(raw.get("state"), str) and raw["state"]:
            evidence = raw.get("evidence", record_evidence)
            normalized[axis] = {
                "state": raw["state"],
                "basis": raw.get("basis", record_basis),
                "evidence": list(evidence) if isinstance(evidence, list) else [],
            }
        else:
            normalized[axis] = {"state": "unknown", "basis": None, "evidence": []}
    return normalized


def load_current_dispositions(root: Path) -> list[dict[str, Any]]:
    """Load append-only current-disposition sidecars under the repository."""

    dispositions: list[dict[str, Any]] = []
    candidates = set(root.rglob("current_disposition.json"))
    dispositions_dir = root / "working" / "current-dispositions"
    if dispositions_dir.is_dir():
        candidates.update(dispositions_dir.glob("*.json"))
    for path in sorted(candidates):
        # Avoid accidental scans through nested VCS or build directories.
        relative = path.relative_to(root)
        if any(part in {".git", ".venv", "node_modules", "target"} for part in relative.parts):
            continue
        value = _read_json(path)
        if not value or value.get("schema") != DISPOSITION_SCHEMA:
            continue
        value = dict(value)
        value["_source_path"] = relative.as_posix()
        dispositions.append(value)
    return dispositions


def _subject_paths(disposition: dict[str, Any]) -> set[str]:
    paths: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("path"), str):
                paths.add(value["path"])
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    subject = disposition.get("subject")
    if isinstance(subject, str):
        paths.add(subject)
    else:
        collect(subject)
    related = disposition.get("related_artifacts")
    if isinstance(related, list):
        for item in related:
            if isinstance(item, str):
                paths.add(item)
            else:
                collect(item)
    return paths


def _subject_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("path"), str):
            yield value
        for nested in value.values():
            yield from _subject_records(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _subject_records(nested)


def _disposition_covers_hashed_path(
    root: Path,
    dispositions: Iterable[dict[str, Any]],
    relative_path: str,
) -> bool:
    """Require a sidecar to bind the exact preserved artifact bytes."""

    artifact = root / relative_path
    if not artifact.is_file():
        return False
    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    for disposition in dispositions:
        for subject in _subject_records(disposition.get("subject")):
            if subject.get("path") != relative_path:
                continue
            expected = subject.get("sha256")
            if isinstance(expected, str) and expected.removeprefix("sha256:") == actual:
                return True
    return False


def _has_disposition_for(
    dispositions: Iterable[dict[str, Any]], relative_path: str
) -> bool:
    return any(relative_path in _subject_paths(disposition) for disposition in dispositions)


def _axis_record(record_id: str, record: dict[str, Any], source_path: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "source_path": source_path,
        "legacy_status": record.get("status"),
        "state_axes": normalize_state_axes(record),
    }


def project_state_axes(root: Path) -> list[dict[str, Any]]:
    """Project explicit axes for backlog, loop, sessions, and dispositions."""

    projected = [
        _axis_record(str(record.get("id", "unknown")), record, record["_source_path"])
        for record in load_backlog(root)
    ]

    loop_path = root / ".governor" / "loop.json"
    if loop := _read_json(loop_path):
        projected.append(_axis_record("@loop", loop, ".governor/loop.json"))

    sessions_dir = root / ".governor" / "sessions"
    for meta_path in sorted(sessions_dir.glob("*/meta.json")):
        if meta := _read_json(meta_path):
            source = meta_path.relative_to(root).as_posix()
            projected.append(
                _axis_record(f"@session:{meta.get('session_id', meta_path.parent.name)}", meta, source)
            )

    for disposition in load_current_dispositions(root):
        subject = disposition.get("subject")
        if isinstance(subject, dict):
            subject_label = str(subject.get("path", disposition["_source_path"]))
        else:
            subject_label = str(subject or disposition["_source_path"])
        projected.append(
            _axis_record(
                f"@disposition:{subject_label}",
                disposition,
                disposition["_source_path"],
            )
        )
    return projected


def summarize_axes(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count explicit/unknown values independently for each axis."""

    counters = {axis: Counter() for axis in AXES}
    for record in records:
        axes = record["state_axes"]
        for axis in AXES:
            counters[axis][axes[axis]["state"]] += 1
    return {
        axis: dict(sorted(counter.items(), key=lambda item: item[0]))
        for axis, counter in counters.items()
    }


def _nightshift_findings(root: Path) -> list[ConsistencyFinding]:
    backlog_path = root / ".governor" / "backlog" / "nightshift-functional-mvp.json"
    status_path = root / "docs" / "campaigns" / "nightshift-functional-mvp" / "STATUS.md"
    backlog = _read_json(backlog_path)
    status = _read_text(status_path)
    if not backlog or not status:
        return []
    live_claim = " ".join(
        str(backlog.get(field, "")) for field in ("open_items", "wake_condition")
    )
    claims_ns1_waiting = bool(
        re.search(r"NS-1.{0,100}(?:STAGED|awaiting.{0,30}approval)", live_claim, re.IGNORECASE)
    )
    status_records_done = bool(
        re.search(r"NS-1 FIRST LIVE RUN\s*[—-]\s*DONE", status, re.IGNORECASE)
    )
    if claims_ns1_waiting and status_records_done:
        return [
            ConsistencyFinding(
                code="nightshift_ns1_stale_backlog",
                severity="contradiction",
                subject="nightshift-functional-mvp/NS-1",
                claim="Current backlog text says NS-1 is staged or awaiting approval.",
                ground_truth="Campaign STATUS records NS-1's approved live run as done and kept.",
                evidence=(
                    ".governor/backlog/nightshift-functional-mvp.json",
                    "docs/campaigns/nightshift-functional-mvp/STATUS.md",
                ),
            )
        ]
    return []


def _transition_findings(root: Path) -> list[ConsistencyFinding]:
    manifest_path = root / ".governor" / "campaigns" / "transition-kernel-pickup.yaml"
    status_path = root / "docs" / "campaigns" / "transition-kernel-pickup" / "STATUS.md"
    manifest = _read_yaml(manifest_path)
    status = _read_text(status_path)
    if not manifest or not status:
        return []
    next_build = manifest.get("next_build")
    if not isinstance(next_build, dict):
        return []
    claims_active = (
        next_build.get("id") == "slice-1b-AGGrantAdapter-at-activation-office-2"
        and next_build.get("status") == "active"
    )
    status_records_done = bool(
        re.search(r"Slice 1b.{0,100}(?:fully on main|ADOPTED AND VERIFIED)", status, re.IGNORECASE)
    )
    disposition = manifest.get("current_disposition")
    disposition_records_done = (
        isinstance(disposition, dict)
        and isinstance(disposition.get("slice_1b"), dict)
        and disposition["slice_1b"].get("status") == "completed"
    )
    if claims_active and status_records_done and not disposition_records_done:
        return [
            ConsistencyFinding(
                code="transition_slice_1b_stale_active",
                severity="contradiction",
                subject="transition-kernel-pickup/slice-1b",
                claim="Discovery manifest calls Slice 1b the active next build.",
                ground_truth="Campaign STATUS records Slice 1b adopted and verified on main.",
                evidence=(
                    ".governor/campaigns/transition-kernel-pickup.yaml",
                    "docs/campaigns/transition-kernel-pickup/STATUS.md",
                ),
            )
        ]
    return []


def _git_ahead_count(root: Path) -> int | None:
    try:
        result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    fields = result.stdout.split()
    if len(fields) != 2:
        return None
    try:
        return int(fields[1])
    except ValueError:
        return None


def _git_campaign_commits_contained(root: Path, commits: list[str]) -> bool | None:
    """Whether every named historical campaign commit is on origin/main."""

    if not commits:
        return None
    for commit in commits:
        try:
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode == 1:
            return False
        if result.returncode != 0:
            return None
    return True


def _ag_admit_push_findings(root: Path) -> list[ConsistencyFinding]:
    manifest_path = root / ".governor" / "campaigns" / "ag-admit-self-build.yaml"
    manifest = _read_yaml(manifest_path)
    if not manifest:
        return []
    state = manifest.get("state")
    claims_unpushed = isinstance(state, dict) and state.get("unpushed") is True
    disposition = manifest.get("current_disposition")
    current_push_state = (
        disposition.get("push_state") if isinstance(disposition, dict) else None
    )
    reconciled_pushed = (
        isinstance(current_push_state, dict) and current_push_state.get("unpushed") is False
    )
    committed = manifest.get("committed")
    commits = [
        str(item["commit"])
        for item in committed
        if isinstance(item, dict) and item.get("commit")
    ] if isinstance(committed, list) else []
    contained = _git_campaign_commits_contained(root, commits)
    # Older/minimal manifests may not enumerate commits; retain the repository
    # ahead check only as a bounded fallback.  Enumerated campaign commits are
    # the stronger claim and remain stable when unrelated work makes HEAD ahead.
    ground_truth_proven = contained is True or (contained is None and _git_ahead_count(root) == 0)
    if reconciled_pushed and contained is False:
        return [
            ConsistencyFinding(
                code="ag_admit_push_successor_not_supported",
                severity="contradiction",
                subject="ag-admit-self-build/push-custody",
                claim="Current disposition says all named campaign commits are pushed.",
                ground_truth="At least one named campaign commit is not contained by origin/main.",
                evidence=(
                    ".governor/campaigns/ag-admit-self-build.yaml",
                    "git merge-base --is-ancestor <campaign-commit> origin/main",
                ),
            )
        ]
    if claims_unpushed and ground_truth_proven and not reconciled_pushed:
        return [
            ConsistencyFinding(
                code="ag_admit_stale_unpushed",
                severity="contradiction",
                subject="ag-admit-self-build/push-custody",
                claim="Discovery manifest says the campaign commits are unpushed.",
                ground_truth=(
                    "Every commit named by the campaign is contained by origin/main."
                    if contained is True
                    else "git reports HEAD has zero commits ahead of origin/main."
                ),
                evidence=(
                    ".governor/campaigns/ag-admit-self-build.yaml",
                    (
                        "git merge-base --is-ancestor <campaign-commit> origin/main"
                        if contained is True
                        else "git rev-list --left-right --count origin/main...HEAD"
                    ),
                ),
            )
        ]
    return []


def _session_findings(
    root: Path, dispositions: list[dict[str, Any]]
) -> list[ConsistencyFinding]:
    findings: list[ConsistencyFinding] = []
    sessions_dir = root / ".governor" / "sessions"
    for meta_path in sorted(sessions_dir.glob("*/meta.json")):
        meta = _read_json(meta_path)
        if not meta or meta.get("state") != "active":
            continue
        session_id = str(meta.get("session_id", meta_path.parent.name))
        ledger = _read_yaml(meta_path.parent / "ledger.yaml") or {}
        workspace = _read_json(meta_path.parent / "workspace.json") or {}
        authority = ledger.get("authority")
        active_threads = workspace.get("active_thread_ids")
        empty_authority = not isinstance(authority, dict) or not authority
        no_active_threads = not isinstance(active_threads, list) or not active_threads
        runtime_log = root / ".governor" / "runtime" / f"{session_id}_events.jsonl"
        no_runtime_log = not runtime_log.is_file()
        rel_meta = meta_path.relative_to(root).as_posix()
        embedded = meta.get("current_disposition")
        reconciled = (
            isinstance(embedded, dict)
            and embedded.get("schema") == DISPOSITION_SCHEMA
        ) or _has_disposition_for(dispositions, rel_meta)
        if empty_authority and no_active_threads and no_runtime_log and not reconciled:
            findings.append(
                ConsistencyFinding(
                    code="session_stale_active_marker",
                    severity="contradiction",
                    subject=session_id,
                    claim="Generic continuity metadata marks the session active.",
                    ground_truth=(
                        "Its ledger has no authority, workspace has no active threads, "
                        "and no matching runtime event stream exists."
                    ),
                    evidence=(
                        rel_meta,
                        (meta_path.parent / "ledger.yaml").relative_to(root).as_posix(),
                        (meta_path.parent / "workspace.json").relative_to(root).as_posix(),
                    ),
                )
            )
    return findings


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _standing_findings(
    standing_db: Path | None, now: datetime
) -> list[ConsistencyFinding]:
    if standing_db is None or not standing_db.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{standing_db}?mode=ro", uri=True)
        rows = connection.execute(
            "SELECT id, state, expires_at FROM grants WHERE state = 'active'"
        ).fetchall()
        connection.close()
    except sqlite3.Error:
        return []

    findings: list[ConsistencyFinding] = []
    now = now.astimezone(timezone.utc)
    for grant_id, state, expires_at in rows:
        expiry = _parse_timestamp(expires_at)
        if expiry is None or expiry > now:
            continue
        findings.append(
            ConsistencyFinding(
                code="standing_expired_materialized_active",
                severity="external_custody",
                subject=f"standing-grant:{grant_id}",
                claim=f"Standing materialized state is {state!r}.",
                ground_truth=(
                    f"expires_at={expires_at} is past; use-time enforcement therefore "
                    "treats the grant as expired."
                ),
                evidence=(str(standing_db), "standing grants.expires_at"),
            )
        )
    return findings


def _queue_findings(root: Path, dispositions: list[dict[str, Any]]) -> list[ConsistencyFinding]:
    status_path = root / "docs" / "campaigns" / "conveyor-dogfood" / "STATUS.md"
    status = _read_text(status_path)
    if not status:
        return []
    completed_markers = {
        "conveyor-dogfood-cd2": r"CD-2 DONE",
        "conveyor-dogfood-cd4": r"CD-4 RUN",
    }
    findings: list[ConsistencyFinding] = []
    specimens = root / "docs" / "campaigns" / "conveyor-dogfood" / "specimens"
    for queue_path in sorted(specimens.glob("*/queue.json")):
        queue = _read_json(queue_path)
        if not queue:
            continue
        queue_id = queue.get("queue_id")
        marker = completed_markers.get(str(queue_id))
        if not marker or not re.search(marker, status, re.IGNORECASE):
            continue
        items = queue.get("items")
        latched = isinstance(items, list) and any(
            isinstance(item, dict) and item.get("operator_approved") is True for item in items
        )
        relative = queue_path.relative_to(root).as_posix()
        reconciled = _disposition_covers_hashed_path(root, dispositions, relative)
        if latched and not reconciled:
            findings.append(
                ConsistencyFinding(
                    code="completed_queue_latch_without_disposition",
                    severity="contradiction",
                    subject=str(queue_id),
                    claim="Completed specimen retains operator_approved=true with no current disposition.",
                    ground_truth=(
                        "Campaign STATUS records the run complete; the historical latch must not "
                        "present as current plan approval."
                    ),
                    evidence=(relative, "docs/campaigns/conveyor-dogfood/STATUS.md"),
                )
            )

        if queue_id != "conveyor-dogfood-cd4":
            continue
        plan_path = queue_path.parent / "plan.md"
        plan = _read_text(plan_path)
        approval_match = re.search(r'approval_ref:\s*["\']([^"\']+)["\']', plan)
        plan_is_approved = bool(re.search(r"governance_status:\s*approved", plan))
        approval_path = queue_path.parent / approval_match.group(1) if approval_match else None
        approval_exists = approval_path is not None and approval_path.is_file()
        if not plan_is_approved or not approval_exists:
            continue
        approval_relative = approval_path.relative_to(root).as_posix()
        plan_relative = plan_path.relative_to(root).as_posix()
        missing_bindings = [
            artifact
            for artifact in (plan_relative, approval_relative)
            if not _disposition_covers_hashed_path(root, dispositions, artifact)
        ]
        if missing_bindings:
            findings.append(
                ConsistencyFinding(
                    code="completed_plan_approval_without_disposition",
                    severity="contradiction",
                    subject=str(queue_id),
                    claim=(
                        "Completed specimen retains an approved exact plan/witness without a "
                        "hash-bound current disposition."
                    ),
                    ground_truth=(
                        "Campaign STATUS and terminal runtime receipts record the run complete; "
                        "retained approval evidence is historical, not current effect authority."
                    ),
                    evidence=tuple(missing_bindings)
                    + ("docs/campaigns/conveyor-dogfood/STATUS.md",),
                )
            )
    return findings


def _loop_findings(root: Path) -> list[ConsistencyFinding]:
    loop_path = root / ".governor" / "loop.json"
    loop = _read_json(loop_path)
    if not loop:
        return []
    current_slice = loop.get("current_slice")
    condition = loop.get("selection_condition")
    if isinstance(condition, dict) and (
        condition.get("state") == "inconsistent_unproven_operator_requirement"
        or condition.get("evidence_status") == "inconsistent"
    ):
        return [
            ConsistencyFinding(
                code="loop_operator_selection_basis_unresolved",
                severity="unresolved_semantic",
                subject=".governor/loop.json selection condition",
                claim="Loop carries a requires-operator selection condition.",
                ground_truth=(
                    "The record explicitly marks that condition inconsistent because no "
                    "custody/rung boundary is evidenced."
                ),
                evidence=(".governor/loop.json",),
            )
        ]
    text = " ".join(
        str(loop.get(field, "")) for field in ("acceptance", "blocked_on", "next_action")
    )
    claims_operator_required = current_slice is None and bool(
        re.search(r"(?:await(?:ing)?|requires?).{0,40}operator.{0,40}select", text, re.IGNORECASE)
    )
    if not claims_operator_required:
        return []

    if isinstance(condition, dict):
        state = condition.get("state")
        evidence = condition.get("evidence")
        if isinstance(evidence, list) and evidence:
            return []

    return [
        ConsistencyFinding(
            code="loop_operator_selection_basis_missing",
            severity="contradiction",
            subject=".governor/loop.json selection condition",
            claim="Loop says the next slice requires operator selection.",
            ground_truth=(
                "No explicit custody/rung boundary or governing evidence is recorded for that "
                "exception to ordinary PLAN selection."
            ),
            evidence=(".governor/loop.json", "docs/loop-protocol.md §8"),
        )
    ]


def collect_consistency_findings(
    root: Path,
    *,
    standing_db: Path | None = None,
    now: datetime | None = None,
) -> list[ConsistencyFinding]:
    """Run the bounded, read-only custody comparisons."""

    root = root.resolve()
    dispositions = load_current_dispositions(root)
    if now is None:
        now = datetime.now(timezone.utc)
    finding_groups = (
        _nightshift_findings(root),
        _transition_findings(root),
        _ag_admit_push_findings(root),
        _session_findings(root, dispositions),
        _standing_findings(standing_db, now),
        _queue_findings(root, dispositions),
        _loop_findings(root),
    )
    return sorted(
        (finding for group in finding_groups for finding in group),
        key=lambda finding: (finding.code, finding.subject),
    )


def default_standing_db(root: Path) -> Path | None:
    """Return the sibling Standing DB when present; never create one."""

    candidate = root.resolve().parent / "standing" / "standing.db"
    return candidate if candidate.is_file() else None


def build_audit(
    root: Path,
    *,
    standing_db: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = project_state_axes(root)
    findings = collect_consistency_findings(root, standing_db=standing_db, now=now)
    return {
        "schema": AUDIT_SCHEMA,
        "measurement_boundary": (
            "Axes are explicit state custody only. Legacy backlog status never implies "
            "selection, plan approval, runtime activity, or effect authority."
        ),
        "records": records,
        "axis_summary": summarize_axes(records),
        "consistency_findings": [finding.to_dict() for finding in findings],
    }
