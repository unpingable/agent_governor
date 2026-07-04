"""state_index_export.v0 — read-only scanner/exporter for AG state-bearing planning docs.

    The export makes state legible; it does not make state true.

Slice 0 of ``specs/gaps/GOV_GAP_STATE_REGISTRY_001.md``. This module scans the prose- and
declared-shaped project-state corpus and emits a deterministic JSON view so that later slices
(a SQLite projection, playbook consumption) have something boring to build on.

Hard boundaries (enforced by what this module does *not* do):
  - No SQLite, no persistent registry, no authority migration, no production behaviour change.
  - Writes ONLY to ``.governor/exports/`` and NEVER rewrites a source doc or the hand-authored
    ``.governor/backlog/*.json``.
  - ``provenance_class`` separates ``declared`` (asserted into ``.governor/`` by an operator/agent)
    from ``observed`` (derived by this scanner from prose). ``execution`` is never emitted here —
    execution state comes only through governed admission.
  - A record is not proof. A ``status`` is not authority. A ``spec_ref`` is a pointer, not validity.

Determinism: records are sorted by ``source_path``; hashes are ``sha256`` of file bytes; no
timestamps or git state leak into the output, so repeated runs are byte-stable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml  # PyYAML (already a project dependency)
except Exception:  # pragma: no cover - yaml is expected present
    yaml = None  # type: ignore[assignment]

SCHEMA = "state_index_export.v0"
SOURCE_NAMESPACE = "ag"
EXPORT_RELPATH = Path(".governor") / "exports" / "state_index_export.v0.json"

# project_lifecycle vocabulary (v0). status is best-effort; unmappable -> None + warning.
PROJECT_STATUSES = frozenset(
    {
        "discovered",
        "triaged",
        "planned",
        "active",
        "blocked",
        "parked",
        "ready_for_review",
        "reviewed",
        "closed",
        "superseded",
        "rejected",
    }
)

# Conservative synonym map. Only high-confidence normalisations; anything else -> unrecognised.
_STATUS_SYNONYMS = {
    "proposed": "planned",
    "planned": "planned",
    "filed": "planned",
    "draft": "discovered",
    "design capture": "triaged",
    "scope": "triaged",
    "candidate": "triaged",
    "provisional": "triaged",
    "triaged": "triaged",
    "discovered": "discovered",
    "active": "active",
    "in progress": "active",
    "wip": "active",
    "blocked": "blocked",
    "parked": "parked",
    "on hold": "parked",
    "ready": "ready_for_review",
    "ready_for_review": "ready_for_review",
    "ready for review": "ready_for_review",
    "reviewed": "reviewed",
    "done": "closed",
    "complete": "closed",
    "completed": "closed",
    "closed": "closed",
    "shipped": "closed",
    "superseded": "superseded",
    "rejected": "rejected",
    "abandoned": "rejected",
}


@dataclass
class StateRecord:
    """One state-bearing artifact, self-describing and portable."""

    provenance_class: str
    id: str
    kind: str
    status: str | None
    title: str | None
    source_path: str
    source_hash: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        # Fixed key order → deterministic serialization (json.dump keeps insertion order).
        return {
            "schema": SCHEMA,
            "source_namespace": SOURCE_NAMESPACE,
            "provenance_class": self.provenance_class,
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "title": self.title,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "warnings": list(self.warnings),
        }


# --------------------------------------------------------------------------- helpers


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _path_id(rel: str) -> str:
    """Stable, path-derived id (POSIX-normalised, extension stripped)."""
    p = rel.replace("\\", "/")
    for suffix in (".md", ".json", ".yaml", ".yml"):
        if p.endswith(suffix):
            return p[: -len(suffix)]
    return p


def _normalize_status(raw: str | None) -> tuple[str | None, str | None]:
    """Return (project_status_or_None, warning_or_None)."""
    if raw is None:
        return None, "status_absent: no status declared"
    cleaned = raw.strip()
    if not cleaned:
        return None, "status_absent: empty status"
    key = re.sub(r"\s+", " ", cleaned.lower()).strip()
    # Try whole-string, then leading token (e.g. "Proposed (v3)" -> "proposed").
    if key in _STATUS_SYNONYMS:
        return _STATUS_SYNONYMS[key], None
    lead = re.split(r"[\s(/,;:]+", key, maxsplit=1)[0]
    if lead in _STATUS_SYNONYMS:
        return _STATUS_SYNONYMS[lead], None
    if key in PROJECT_STATUSES:
        return key, None
    return None, f"status_unrecognized: {cleaned!r}"


def _md_title(text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or None
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(">"):
            return s
    return None


_STATUS_HEADING_RE = re.compile(r"^#{1,6}\s+status\b", re.IGNORECASE)
_STATUS_INLINE_RE = re.compile(r"\*\*status:?\*\*[:\s]*(.+)", re.IGNORECASE)
_STATUS_PLAIN_RE = re.compile(r"^status:\s*(.+)", re.IGNORECASE)


def _md_status(text: str) -> str | None:
    lines = text.splitlines()
    # Inline "**Status:** ..." anywhere near the top (first 30 lines).
    for line in lines[:30]:
        m = _STATUS_INLINE_RE.search(line)
        if m:
            return _clip_status(m.group(1))
        m = _STATUS_PLAIN_RE.match(line.strip())
        if m:
            return _clip_status(m.group(1))
    # "## Status" heading → first non-empty following line.
    for i, line in enumerate(lines):
        if _STATUS_HEADING_RE.match(line.strip()):
            for follow in lines[i + 1 :]:
                s = follow.strip()
                if s:
                    return _clip_status(s)
            break
    return None


def _clip_status(raw: str) -> str:
    # Strip markdown emphasis/backticks and trailing prose after the first sentence-ish clause.
    s = raw.strip().strip("*`").strip()
    s = re.split(r"[.—\-]{1,}\s", s, maxsplit=1)[0]
    return s.strip()


# --------------------------------------------------------------------------- classification


def _classify_md_kind(rel: str, name: str) -> tuple[str, list[str]]:
    low = name.lower()
    warnings: list[str] = []
    if rel.startswith("specs/gaps/"):
        return "gap", warnings
    if rel.startswith("docs/playbooks/"):
        if "exit-ticket" in low or "review" in low or "contract" in low:
            return "review_gate", warnings
        return "playbook", warnings
    if rel.startswith("docs/campaigns/"):
        if name == "DECISIONS.md":
            return "operator_decision", warnings
        if name == "NEXT.md":
            return "planned_slice", warnings
        if name in ("CAMPAIGN.md", "STATUS.md", "INVENTORY.md", "TRANSPORT.md"):
            return "work_packet", warnings
        warnings.append("kind_ambiguous: unrecognised campaign file, fell back to 'other'")
        return "other", warnings
    if rel.startswith("docs/roadmaps/tools/"):
        return "tool_roadmap", warnings
    if rel.startswith("docs/roadmaps/"):
        # Hub files (README/ROUTING/PARKED/CONSOLIDATION) are scanned for
        # legibility but deliberately NOT given kinds of their own — one new
        # kind per the CD-2 fence; a hub taxonomy is a later, separate call.
        warnings.append("kind_ambiguous: roadmap hub file, fell back to 'other'")
        return "other", warnings
    if rel.startswith("working/"):
        if "parked" in low or low.startswith("candidate-") or "_parked" in low:
            return "parked_candidate", warnings
        if low.startswith("resume_") or low.startswith("exit_"):
            return "work_packet", warnings
        warnings.append("kind_ambiguous: working/ note, fell back to 'other'")
        return "other", warnings
    warnings.append("kind_ambiguous: unrecognised path, fell back to 'other'")
    return "other", warnings


# --------------------------------------------------------------------------- record builders


def _record_from_markdown(root: Path, path: Path, provenance: str) -> StateRecord:
    rel = path.relative_to(root).as_posix()
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    kind, warnings = _classify_md_kind(rel, path.name)
    title = _md_title(text)
    if title is None:
        warnings.append("title_missing: no heading or first line found")
    status, status_warn = _normalize_status(_md_status(text))
    if status_warn:
        warnings.append(status_warn)
    return StateRecord(
        provenance_class=provenance,
        id=_path_id(rel),
        kind=kind,
        status=status,
        title=title,
        source_path=rel,
        source_hash=_sha256(raw),
        warnings=warnings,
    )


def _record_from_backlog_json(root: Path, path: Path) -> StateRecord:
    rel = path.relative_to(root).as_posix()
    raw = path.read_bytes()
    warnings: list[str] = []
    data: dict = {}
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            warnings.append("parse_error: backlog item is not a JSON object")
            data = {}
    except Exception as exc:  # noqa: BLE001 - report, don't crash the scan
        warnings.append(f"parse_error: {exc}")
    item_id = str(data.get("id") or _path_id(rel))
    title = str(data.get("id") or _path_id(rel))
    status, status_warn = _normalize_status(data.get("status"))
    if status_warn:
        warnings.append(status_warn)
    # Divergence check: does the cited spec_ref resolve to a real file? Direction unattested.
    spec_ref = data.get("spec_ref")
    if isinstance(spec_ref, str) and spec_ref.strip():
        ref_path = spec_ref.split("§")[0].split("#")[0].strip()
        if ref_path and not (root / ref_path).exists():
            warnings.append(
                f"spec_ref_unresolved: declared backlog item cites {ref_path!r} "
                "which is not present (declared/observed divergence, direction unattested)"
            )
    return StateRecord(
        provenance_class="declared",
        id=item_id,
        kind="backlog_item",
        status=status,
        title=title,
        source_path=rel,
        source_hash=_sha256(raw),
        warnings=warnings,
    )


def _record_from_yaml(root: Path, path: Path, kind: str, provenance: str) -> StateRecord:
    rel = path.relative_to(root).as_posix()
    raw = path.read_bytes()
    warnings: list[str] = []
    data: dict = {}
    if yaml is None:
        warnings.append("parse_error: PyYAML unavailable")
    else:
        try:
            loaded = yaml.safe_load(raw.decode("utf-8"))
            if isinstance(loaded, dict):
                data = loaded
            elif loaded is not None:
                warnings.append("parse_error: YAML root is not a mapping")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"parse_error: {exc}")
    campaign = data.get("campaign") if isinstance(data.get("campaign"), str) else None
    status: str | None = None
    if kind == "waiver":
        # GRANTS.yaml lives under docs/campaigns/<name>/ (prose corpus → observed).
        camp_dir = path.parent.name
        item_id: str = f"{camp_dir}:grants"
        title: str = f"Grants — {camp_dir}"
    else:  # campaign discovery manifest (.governor/campaigns/ → declared)
        item_id = campaign or _path_id(rel)
        title = campaign or _path_id(rel)
        nb = data.get("next_build")
        status_raw = nb.get("status") if isinstance(nb, dict) else None
        status, status_warn = _normalize_status(status_raw if isinstance(status_raw, str) else None)
        if status_warn:
            warnings.append(status_warn)
    return StateRecord(
        provenance_class=provenance,
        id=str(item_id),
        kind=kind,
        status=status,
        title=str(title),
        source_path=rel,
        source_hash=_sha256(raw),
        warnings=warnings,
    )


# --------------------------------------------------------------------------- scan


def _scan_targets(root: Path) -> list[tuple[Path, str, str]]:
    """Return (path, provenance_class, reader) tuples in a stable order.

    reader ∈ {"md", "backlog_json", "campaign_yaml", "grants_yaml"}.
    """
    out: list[tuple[Path, str, str]] = []

    gaps = root / "specs" / "gaps"
    if gaps.is_dir():
        for p in sorted(gaps.glob("*.md")):
            out.append((p, "observed", "md"))

    playbooks = root / "docs" / "playbooks"
    if playbooks.is_dir():
        for p in sorted(playbooks.glob("*.md")):
            out.append((p, "observed", "md"))

    roadmaps = root / "docs" / "roadmaps"
    if roadmaps.is_dir():
        for p in sorted(roadmaps.glob("*.md")):
            out.append((p, "observed", "md"))
        tools = roadmaps / "tools"
        if tools.is_dir():
            for p in sorted(tools.glob("*.md")):
                out.append((p, "observed", "md"))

    campaigns = root / "docs" / "campaigns"
    if campaigns.is_dir():
        for camp in sorted(campaigns.glob("*")):
            if not camp.is_dir():
                continue
            for name in ("CAMPAIGN", "STATUS", "NEXT", "DECISIONS", "INVENTORY", "TRANSPORT"):
                p = camp / f"{name}.md"
                if p.exists():
                    out.append((p, "observed", "md"))
            g = camp / "GRANTS.yaml"
            if g.exists():
                out.append((g, "observed", "grants_yaml"))

    working = root / "working"
    if working.is_dir():
        for p in sorted(working.glob("*.md")):
            out.append((p, "observed", "md"))

    backlog = root / ".governor" / "backlog"
    if backlog.is_dir():
        for p in sorted(backlog.glob("*.json")):
            out.append((p, "declared", "backlog_json"))

    gov_campaigns = root / ".governor" / "campaigns"
    if gov_campaigns.is_dir():
        for p in sorted(gov_campaigns.glob("*.yaml")):
            out.append((p, "declared", "campaign_yaml"))

    return out


def export_records(root: str | Path) -> list[dict]:
    """Scan the corpus and return deterministic, sorted record dicts.

    Read-only. Never writes. Never raises on a malformed source file — parse failures become
    ``parse_error`` warnings on the offending record.
    """
    root = Path(root).resolve()
    records: list[StateRecord] = []
    for path, provenance, reader in _scan_targets(root):
        if reader == "md":
            records.append(_record_from_markdown(root, path, provenance))
        elif reader == "backlog_json":
            records.append(_record_from_backlog_json(root, path))
        elif reader == "campaign_yaml":
            records.append(_record_from_yaml(root, path, "work_packet", provenance))
        elif reader == "grants_yaml":
            records.append(_record_from_yaml(root, path, "waiver", provenance))
    records.sort(key=lambda r: r.source_path)
    return [r.to_dict() for r in records]


def write_export(root: str | Path, out_path: str | Path | None = None) -> Path:
    """Write the export to ``.governor/exports/state_index_export.v0.json`` (byte-stable)."""
    root = Path(root).resolve()
    records = export_records(root)
    dest = Path(out_path) if out_path is not None else (root / EXPORT_RELPATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(records, indent=2, ensure_ascii=False) + "\n"
    dest.write_text(text, encoding="utf-8")
    return dest
