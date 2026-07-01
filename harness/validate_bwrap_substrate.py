# SPDX-License-Identifier: Apache-2.0
"""Live C1–C10 substrate compatibility validation — minimal fenced entrypoint (OUTSIDE AG).

Authorized by `docs/playbooks/next-gate-selection-review.md` (operator pass 2026-07-01,
with amendments). This is an **evidence run, not implementation**. Its ONLY job is to run the
*existing* bwrap backend's pre-flight battery against the real host, declare the host/substrate
facts, capture a probe transcript, and write **one** tainted audit record — while the backend
**refuses live by construction** (C11 has no compiled seccomp filter in v0).

What this is NOT (hard fences — see the review's operator pass):

- **No actor.** The only subprocesses launched are `bwrap` probe commands and read-only host
  detection (`uname`, `bwrap --version`, reads of `/proc`). No Claude/Codex/echo/actor, no
  `run`/`spawn`/`run_once`. This file is deliberately **not** `harness/run.py` and does not
  resemble it.
- **No H2, no seccomp implementation, no operational effect, no live admission.** This module
  never calls `admit_live`, never mints an attestation, and never asserts
  `confirms_isolation=True`. It *consumes* the backend's attestation, which refuses in v0.
- **C11 unavailable forces refusal.** If the backend ever reported `confirms_isolation=True`
  (impossible in v0), this entrypoint **raises** rather than writing an admission record.

What a full C1–C10 pass with C11 unavailable *is*: a **successful refusal plus partial
substrate evidence** — the cage was correctly refused, and the C1–C10 witness machinery gained
its first *live substrate compatibility* evidence. That is not live admission. Neither is this
module's green test suite: tests exercise parser / recording / refusal logic on synthetic
inputs and are **not live testimony**.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .bwrap_cage import (
    BWRAP_BASE_ARGS,
    ENV_LEAK_SENTINEL,
    ORDERED_FACT_IDS,
    PROBE_SPECS,
    BwrapCage,
    CageRunAttestation,
)
from .cage import audit_store_root, run_dir

RECORD_KIND = "bwrap_substrate_validation.v0"
RECORD_FILENAME = "substrate_validation.json"

# Outcome vocabulary (closed). None of these is an admission.
OUTCOME_HOST_UNSUPPORTED = "host_unsupported_refusal"
OUTCOME_SUCCESSFUL_REFUSAL_PARTIAL = "successful_refusal_partial_substrate_evidence"
OUTCOME_REFUSED_INCOMPLETE = "refused_incomplete_substrate"

# A green suite / a green C1–C10 battery / this record are NOT live testimony. Carried in the
# record so the artifact cannot be misread downstream.
NOT_LIVE_TESTIMONY = (
    "This record is NOT live testimony of a live-admissible cage. C11 (seccomp) is "
    "unwitnessable in the v0 backend, so `confirms_isolation` is False by construction. A "
    "full C1–C10 pass here is a successful refusal plus partial substrate evidence, never "
    "admission. Pushed code, synthetic (FakeProber) compatibility, shape/constitution "
    "approval, and actor claims are likewise not live testimony."
)

_MAX_CAPTURE = 4000  # bytes of stdout/stderr retained per command in the transcript


class SubstrateValidationRefused(RuntimeError):
    """Raised if the backend ever reports a live-admissible cage. The entrypoint refuses to
    write an admission record; C11 unavailable must force refusal."""


# --------------------------------------------------------------------------- #
# Command transcript capture (read-only host probes + bwrap probe commands only).
# --------------------------------------------------------------------------- #


def _capture(cmd: list[str], *, timeout_s: int = 10) -> dict[str, Any]:
    """Run one command, capturing argv + exit + (truncated) output for the transcript.
    Never raises for a nonzero/failed command — a failed probe is evidence, not an error."""
    entry: dict[str, Any] = {"cmd": list(cmd)}
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
        entry["returncode"] = r.returncode
        entry["stdout"] = r.stdout[:_MAX_CAPTURE].decode("utf-8", "replace")
        entry["stderr"] = r.stderr[:_MAX_CAPTURE].decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        entry["returncode"] = None
        entry["error"] = f"timeout after {timeout_s}s"
    except (OSError, subprocess.SubprocessError) as exc:
        entry["returncode"] = None
        entry["error"] = f"could not run: {exc}"
    return entry


def _read_proc(path: str) -> Optional[str]:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# Substrate declaration (the run must name the ground it stood on).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SubstrateFacts:
    host_id: str
    host_class: str  # operator-declared: bare_metal | vm | container | ci | unknown
    kernel: str
    bwrap_version: Optional[str]
    userns_available: bool
    seccomp_available: bool
    nested_sandbox: str  # "yes" | "no" | "unknown" (best-effort detection)
    nested_signals: tuple[str, ...]
    audit_store_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "host_id": self.host_id,
            "host_class": self.host_class,
            "kernel": self.kernel,
            "bwrap_version": self.bwrap_version,
            "userns_available": self.userns_available,
            "seccomp_available": self.seccomp_available,
            "nested_sandbox": self.nested_sandbox,
            "nested_signals": list(self.nested_signals),
            "audit_store_path": self.audit_store_path,
        }


def _detect_nested() -> tuple[str, tuple[str, ...], list[dict[str, Any]]]:
    """Best-effort nested-sandbox detection. Honest tri-state: strong signal → 'yes',
    explicit absence of markers → 'no', otherwise 'unknown'. Signals + transcript returned so
    the operator can override the classification with judgement."""
    signals: list[str] = []
    transcript: list[dict[str, Any]] = []

    if Path("/.dockerenv").exists():
        signals.append("/.dockerenv present")
    cgroup = _read_proc("/proc/1/cgroup") or ""
    transcript.append({"cmd": ["cat", "/proc/1/cgroup"], "stdout": cgroup[:_MAX_CAPTURE]})
    for marker in ("docker", "lxc", "containerd", "kubepods", "buildkit"):
        if marker in cgroup:
            signals.append(f"/proc/1/cgroup mentions {marker}")
    userns_clone = _read_proc("/proc/sys/kernel/unprivileged_userns_clone")
    if userns_clone == "0":
        signals.append("unprivileged_userns_clone=0 (userns restricted)")

    if signals:
        return "yes", tuple(signals), transcript
    # No strong markers. Only claim 'no' if we could actually read the markers.
    if cgroup or userns_clone is not None:
        return "no", (), transcript
    return "unknown", (), transcript


def detect_substrate(
    *, host_id: Optional[str], host_class: str, transcript: list[dict[str, Any]]
) -> SubstrateFacts:
    """Gather the mandatory substrate facts, appending each detection command to `transcript`.
    `host_id` / `host_class` are operator-declared (auto-filled conservatively if omitted)."""
    hid = host_id or socket.gethostname() or "unknown-host"

    uname = _capture(["uname", "-a"])
    transcript.append(uname)
    kernel = (uname.get("stdout") or "").strip() or platform.platform()

    bwrap = shutil.which("bwrap")
    bwrap_version: Optional[str] = None
    if bwrap:
        ver = _capture([bwrap, "--version"])
        transcript.append(ver)
        bwrap_version = (ver.get("stdout") or "").strip() or None

    userns_clone = _read_proc("/proc/sys/kernel/unprivileged_userns_clone")
    max_userns = _read_proc("/proc/sys/user/max_user_namespaces")
    userns_available = userns_clone == "1" or (
        userns_clone is None and (max_userns or "0").isdigit() and int(max_userns or "0") > 0
    )
    seccomp_available = "Seccomp:" in (_read_proc("/proc/self/status") or "")

    nested, signals, nested_transcript = _detect_nested()
    transcript.extend(nested_transcript)

    return SubstrateFacts(
        host_id=hid,
        host_class=host_class,
        kernel=kernel,
        bwrap_version=bwrap_version,
        userns_available=userns_available,
        seccomp_available=seccomp_available,
        nested_sandbox=nested,
        nested_signals=signals,
        audit_store_path=str(audit_store_root()),
    )


# --------------------------------------------------------------------------- #
# Probe transcript (exact commands the backend runs, captured independently).
# --------------------------------------------------------------------------- #


def probe_argv(fact_id: str, bwrap: str) -> Optional[list[str]]:
    """The exact bwrap argv for one inner-probe fact (C1–C8), built from the backend's own
    exported constants so the transcript cannot drift from what the backend runs. C9/C10 are
    prober-lifecycle guarantees and C11 is unwitnessable → no standalone argv."""
    spec = PROBE_SPECS.get(fact_id)
    if spec is None:
        return None
    return [bwrap, *BWRAP_BASE_ARGS, "--", *spec.inner]


def smoke_argv(bwrap: str) -> list[str]:
    """The cage-smoke command (does an isolated cage start at all)."""
    return [bwrap, *BWRAP_BASE_ARGS, "--", "/bin/true"]


def capture_probe_transcript(host_ok: bool) -> list[dict[str, Any]]:
    """Capture the cage-smoke and, only if the host can start a cage, each C1–C8 inner probe.
    Uses the backend's exported argv constants. Runs bwrap probe commands only — no actor.
    On a non-capable host the smoke transcript (the failure) is the meaningful evidence."""
    bwrap = shutil.which("bwrap")
    transcript: list[dict[str, Any]] = []
    if not bwrap:
        transcript.append({"cmd": ["bwrap"], "error": "bwrap not found on PATH"})
        return transcript
    smoke = _capture(smoke_argv(bwrap))
    smoke["fact_id"] = "cage_smoke"
    transcript.append(smoke)
    if not host_ok:
        return transcript  # cage won't start; do not attempt inner probes
    env_note = {"note": f"probes run with {ENV_LEAK_SENTINEL}=1 in parent env (C8 strips it)"}
    transcript.append(env_note)
    for fid in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"):
        argv = probe_argv(fid, bwrap)
        if argv is None:
            continue
        entry = _capture(argv)
        entry["fact_id"] = fid
        transcript.append(entry)
    return transcript


# --------------------------------------------------------------------------- #
# Refusal classification (pure — the part tests pin).
# --------------------------------------------------------------------------- #


def classify_outcome(
    *, confirms_isolation: bool, host_ok: bool, witnessed_fact_ids: frozenset[str]
) -> str:
    """Classify the run. Never returns an admission — `confirms_isolation=True` is a hard
    error (raised by the caller), not an outcome. C11 unavailable ⇒ refusal, always."""
    if confirms_isolation:
        raise SubstrateValidationRefused(
            "backend reported confirms_isolation=True; C11 must be unwitnessable in v0"
        )
    if not host_ok:
        return OUTCOME_HOST_UNSUPPORTED
    c1_c10 = {f"C{i}" for i in range(1, 11)}
    if c1_c10 <= witnessed_fact_ids and "C11" not in witnessed_fact_ids:
        return OUTCOME_SUCCESSFUL_REFUSAL_PARTIAL
    return OUTCOME_REFUSED_INCOMPLETE


# --------------------------------------------------------------------------- #
# Record builder (pure — the part tests pin).
# --------------------------------------------------------------------------- #


def build_validation_record(
    *,
    run_id: str,
    substrate: SubstrateFacts,
    run_attestation: CageRunAttestation,
    detection_transcript: list[dict[str, Any]],
    probe_transcript: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the single tainted audit record. Pure: no IO, no subprocess. Raises if the
    attestation is a live admission (C11 must force refusal)."""
    confirms = run_attestation.confirms_isolation
    host_ok = run_attestation.host_support.ok
    witnessed = frozenset(w.fact_id for w in run_attestation.witnesses if w.witnessed)
    outcome = classify_outcome(
        confirms_isolation=confirms, host_ok=host_ok, witnessed_fact_ids=witnessed
    )
    return {
        "record_kind": RECORD_KIND,
        "run_id": run_id,
        "generated_by": "harness/validate_bwrap_substrate.py",
        "not_live_testimony": NOT_LIVE_TESTIMONY,
        "substrate": substrate.as_dict(),
        "commands": {
            "detection": detection_transcript,
            "probes": probe_transcript,
        },
        "cage_attestation": run_attestation.to_evidence_dict(),
        "decision": {
            "confirms_isolation": confirms,
            "host_supported": host_ok,
            "c11_witnessed": "C11" in witnessed,
            "mandatory_c11_refusal": True,
            "witnessed_facts": [f for f in ORDERED_FACT_IDS if f in witnessed],
            "unwitnessed_facts": list(run_attestation.missing_or_unwitnessed()),
            "outcome": outcome,
            "live_admission": False,
        },
    }


def persist_validation_record(record: dict[str, Any]) -> Path:
    """Write the ONE tainted audit record under the harness audit store (AG-never-ingested).
    Referenced by run id / digest only; never imported as AG authority."""
    d = run_dir(record["run_id"])
    d.mkdir(parents=True, exist_ok=True)
    out = d / RECORD_FILENAME
    out.write_text(json.dumps(record, indent=2, sort_keys=True))
    return out


# --------------------------------------------------------------------------- #
# The run (thin orchestration; no actor, no admission).
# --------------------------------------------------------------------------- #


def run_validation(
    *,
    run_id: str,
    host_id: Optional[str] = None,
    host_class: str = "unknown",
    cage: Optional[BwrapCage] = None,
) -> tuple[dict[str, Any], Path]:
    """Detect substrate → evaluate the existing backend (authoritative attestation) → capture
    transcripts → build + persist ONE tainted audit record. Returns (record, path).

    Never admits live: it reads `cage.evaluate()` and refuses (raises) if that ever reports a
    live-admissible cage. Runs no actor."""
    cage = cage or BwrapCage()
    detection_transcript: list[dict[str, Any]] = []
    substrate = detect_substrate(
        host_id=host_id, host_class=host_class, transcript=detection_transcript
    )
    run_attestation = cage.evaluate(run_id=run_id)
    if run_attestation.confirms_isolation:  # defensive: C11 must force refusal
        raise SubstrateValidationRefused(
            "backend attested a live-admissible cage; refusing to write an admission record"
        )
    probe_transcript = capture_probe_transcript(run_attestation.host_support.ok)
    record = build_validation_record(
        run_id=run_id,
        substrate=substrate,
        run_attestation=run_attestation,
        detection_transcript=detection_transcript,
        probe_transcript=probe_transcript,
    )
    path = persist_validation_record(record)
    return record, path


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="validate-bwrap-substrate",
        description="Live C1–C10 substrate compatibility validation (evidence run; refuses "
        "live by construction in v0). Runs no actor.",
    )
    p.add_argument("--run-id", required=True, help="run id for the tainted audit record")
    p.add_argument("--host-id", default=None, help="operator-declared host identity")
    p.add_argument(
        "--host-class",
        default="unknown",
        choices=["bare_metal", "vm", "container", "ci", "unknown"],
        help="operator-declared host class",
    )
    p.add_argument("--print", action="store_true", help="print the record to stdout")
    args = p.parse_args(argv)

    record, path = run_validation(
        run_id=args.run_id, host_id=args.host_id, host_class=args.host_class
    )
    outcome = record["decision"]["outcome"]
    print(f"substrate validation: {outcome} (live_admission=False)")
    print(f"tainted audit record: {path}")
    if args.print:
        print(json.dumps(record, indent=2, sort_keys=True))
    # Exit 0: a refusal is the expected, successful outcome of this gate. The record — not the
    # exit code — carries the verdict. (A live admission would have raised before here.)
    return 0


__all__ = [
    "RECORD_KIND",
    "RECORD_FILENAME",
    "OUTCOME_HOST_UNSUPPORTED",
    "OUTCOME_SUCCESSFUL_REFUSAL_PARTIAL",
    "OUTCOME_REFUSED_INCOMPLETE",
    "NOT_LIVE_TESTIMONY",
    "SubstrateValidationRefused",
    "SubstrateFacts",
    "detect_substrate",
    "probe_argv",
    "smoke_argv",
    "capture_probe_transcript",
    "classify_outcome",
    "build_validation_record",
    "persist_validation_record",
    "run_validation",
    "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
