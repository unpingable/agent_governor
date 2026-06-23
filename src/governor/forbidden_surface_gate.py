# SPDX-License-Identifier: Apache-2.0
"""
ForbiddenSurfaceGate — the semantic companion to DiffPathScopeGate.

DiffPathScopeGate answers "are the touched paths in scope?" (path authority).
ForbiddenSurfaceGate answers "does this diff mutate a forbidden *semantic* surface?".
Path authority is necessary but not sufficient: a file can be inside the path grant while
the *kind* of change to it is forbidden (Slice 3 proved this — gate_receipt.py was inside
the path grant, but the closed-enum change was forbidden). Without this gate a
self-correcting loop is a very obedient burglar.

Design (capsule seed docs/campaigns/ag-admit-self-build/NEXT.md):
- A classifier over a DECLARED forbidden-surface list — NOT a general semantic oracle.
  Literal markers only; the receipt records exactly what was observed.
- Conservative: a forbidden-surface FILE touched without a clear marker, or an unparseable
  diff, → CANNOT_TESTIFY (never ADMIT). A clear marker hit → BLOCK. No forbidden file
  touched → PROCEED.
- Satisfies the governed_dispatch.PreflightClient Protocol; its source verdict rides in
  raw.source_verdict and is projected by the existing ag_admit projection. The dumb
  conductor is unchanged — detected surfaces ride in block_reasons, which it already records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ag_admit import SOURCE_BLOCK, SOURCE_CANNOT_TESTIFY, SOURCE_PROCEED
from .governed_dispatch import PreflightDecision, PreflightRequest

REASON_SEMANTIC_FORBIDDEN = "semantic_surface_forbidden"
REASON_SEMANTIC_AMBIGUOUS = "semantic_surface_ambiguous"
REASON_NO_FORBIDDEN_SURFACE = "no_forbidden_surface"
REASON_CANNOT_OBSERVE_DIFF = "cannot_observe_diff"


@dataclass(frozen=True)
class ForbiddenSurface:
    """One declared forbidden semantic surface.

    Modified when a touched file ends with one of `path_suffixes` AND a changed (+/-) diff
    line contains one of `markers`. If `markers` is empty, the file itself is forbidden to
    touch (path match alone is a modification).
    """

    surface_id: str
    path_suffixes: tuple[str, ...]
    markers: tuple[str, ...] = ()


# Declared forbidden-surface list (mirrors GRANTS.yaml forbidden_surfaces). Literal markers.
DEFAULT_FORBIDDEN_SURFACES: tuple[ForbiddenSurface, ...] = (
    ForbiddenSurface(
        "stepverdict_projection",
        ("governor/ag_admit.py",),
        ("class StepVerdict", "def project_source_verdict", "_ADMIT_SOURCES", "_REJECT_SOURCES"),
    ),
    ForbiddenSurface(
        "preflight_contract",
        ("governor/governed_dispatch.py",),
        ("class PreflightClient", "class PreflightRequest", "class PreflightDecision", "def governed_dispatch"),
    ),
    ForbiddenSurface(
        "conductor_authority",
        ("ag_admit_conductor.py",),
        ("_VERDICT_TABLE", "def conduct"),
    ),
    ForbiddenSurface(
        "closed_receipt_enums",
        ("governor/gate_receipt.py",),
        ("VALID_VERDICTS", "VALID_RECEIPT_ROLES", "VALID_NON_DISCHARGE_KINDS", "VALID_HORIZON_KINDS"),
    ),
    ForbiddenSurface(
        "receipt_emission_semantics",
        ("governor/gate_receipt.py",),
        ("def create_receipt", "def _compute_receipt_id", "def canonical_json", "RECEIPT_SCHEMA_VERSION"),
    ),
    ForbiddenSurface(
        "loop_state",
        (".governor/loop.json",),
        (),  # whole-file forbidden: any touch is a modification
    ),
    ForbiddenSurface(
        "ci_accept_semantics",
        ("governor/ci.py",),
        ("accepts_waiver_admitted", "_receipt_acceptable", "_is_waiver_admission_shaped"),
    ),
)


def _scan_diff(diff_text: str) -> tuple[list[str] | None, list[str]]:
    """Return (touched_files, changed_lines). touched_files is None if no diff header.

    touched_files: repo-relative paths from ---/+++/diff --git headers (a/ b/ and /dev/null
    stripped). changed_lines: the bodies of added/removed lines (excluding +++/--- headers).
    """
    files: list[str] = []
    changed: list[str] = []
    saw_header = False

    def _strip(token: str) -> str | None:
        token = token.split("\t", 1)[0].strip()
        if token.startswith(("a/", "b/")):
            token = token[2:]
        if not token or token == "/dev/null":
            return None
        return token

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            saw_header = True
            for p in line[len("diff --git ") :].split():
                sp = _strip(p)
                if sp:
                    files.append(sp)
        elif line.startswith("--- ") or line.startswith("+++ "):
            saw_header = True
            sp = _strip(line[4:])
            if sp:
                files.append(sp)
        elif line.startswith("@@"):
            continue
        elif line.startswith("+") or line.startswith("-"):
            changed.append(line[1:])

    if not saw_header:
        return None, []
    return files, changed


class ForbiddenSurfaceGate:
    """Classify a diff against the declared forbidden semantic surfaces."""

    GATE_NAME = "ForbiddenSurfaceGate"
    OBSERVATION_METHOD = "unidiff_path_and_hunk_scan"

    def __init__(self, surfaces: tuple[ForbiddenSurface, ...] = DEFAULT_FORBIDDEN_SURFACES):
        self.surfaces = tuple(surfaces)

    def _decision(
        self,
        *,
        decision: str,
        source_verdict: str,
        reason: str,
        observed_paths: list[str],
        detected: list[dict[str, Any]] | None = None,
        ambiguous: list[str] | None = None,
    ) -> PreflightDecision:
        raw: dict[str, Any] = {
            "source_gate": self.GATE_NAME,
            "source_verdict": source_verdict,
            "reason": reason,
            "observed_paths": observed_paths,
            "observation_method": self.OBSERVATION_METHOD,
            "detected_surfaces": detected or [],
            "ambiguous_surfaces": ambiguous or [],
        }
        block_reasons: list[dict[str, Any]] = []
        if decision == "blocked":
            br: dict[str, Any] = {"kind": reason, "source_verdict": source_verdict}
            if detected:
                br["detected_surfaces"] = detected
            if ambiguous:
                br["ambiguous_surfaces"] = ambiguous
            block_reasons.append(br)
        return PreflightDecision(
            decision=decision, mode="enforce", block_reasons=block_reasons, raw=raw
        )

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        diff = request.args.get("diff")
        if not isinstance(diff, str) or not diff.strip():
            return self._decision(
                decision="blocked",
                source_verdict=SOURCE_CANNOT_TESTIFY,
                reason=REASON_CANNOT_OBSERVE_DIFF,
                observed_paths=[],
            )

        files, changed_lines = _scan_diff(diff)
        if files is None:
            return self._decision(
                decision="blocked",
                source_verdict=SOURCE_CANNOT_TESTIFY,
                reason=REASON_CANNOT_OBSERVE_DIFF,
                observed_paths=[],
            )
        observed = sorted(set(files))

        detected: list[dict[str, Any]] = []
        ambiguous: list[str] = []
        for surface in self.surfaces:
            file_hit = any(
                f.endswith(suf) for f in observed for suf in surface.path_suffixes
            )
            if not file_hit:
                continue
            if not surface.markers:
                detected.append({"surface_id": surface.surface_id, "marker": None})
                continue
            hit_marker = next(
                (m for m in surface.markers if any(m in cl for cl in changed_lines)),
                None,
            )
            if hit_marker is not None:
                detected.append({"surface_id": surface.surface_id, "marker": hit_marker})
            else:
                ambiguous.append(surface.surface_id)

        if detected:
            return self._decision(
                decision="blocked",
                source_verdict=SOURCE_BLOCK,
                reason=REASON_SEMANTIC_FORBIDDEN,
                observed_paths=observed,
                detected=detected,
                ambiguous=ambiguous or None,
            )
        if ambiguous:
            # A sacred file was touched but no declared marker matched — the classifier
            # cannot testify the change is benign (it is not an oracle). Escalate, never ADMIT.
            return self._decision(
                decision="blocked",
                source_verdict=SOURCE_CANNOT_TESTIFY,
                reason=REASON_SEMANTIC_AMBIGUOUS,
                observed_paths=observed,
                ambiguous=ambiguous,
            )
        return self._decision(
            decision="allow",
            source_verdict=SOURCE_PROCEED,
            reason=REASON_NO_FORBIDDEN_SURFACE,
            observed_paths=observed,
        )

    async def record(
        self,
        request: PreflightRequest,
        result_status: str,
        preflight_token: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "recorded": True,
            "gate": self.GATE_NAME,
            "result_status": result_status,
            "record_id": record_id,
        }
