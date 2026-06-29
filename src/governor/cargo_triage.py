# SPDX-License-Identifier: Apache-2.0
"""Cargo/rustc failure-triage driver (Slice 0) — generic, on-prem, frontier-free.

Runs a `cargo` command, captures the build environment, splits the rustc/cargo
diagnostics into per-error units, and triages each through the **existing** local
candidate worker (`local_candidate.triage_failure`, the ratified failure_triage lane).

Deliberately generic and aggressively boring: it knows nothing about any specific
repo, so it can run against a SECRET tree (e.g. an NQ mac port) **entirely on the
operator's machines** — local model only, no frontier call, no repo mutation, no
claim that anything "works". It produces *candidate descriptions of compiler/test
failures*. It is not a port bot.

Custody:
- **No frontier call.** Uses an injected `LocalModelClient` (local Ollama).
- **No source mutation.** `cargo check/build/test` write only to `target/`, never source.
- **No authority.** Every output is a non-authoritative candidate receipt; the worker
  hard-refuses any "tests pass / safe to commit / port works" claim.

Slice 0 reuses `failure_triage` unchanged. The NQ-specific `platform_specificity`
field (mac_only | rust_version | dependency | environment | unknown) is the named
**Slice 1** increment, not built here.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

from .local_candidate import (
    TASK_FAILURE_TRIAGE,
    LocalCandidateReceipt,
    LocalCandidateRequest,
    LocalModelClient,
    triage_failure,
)

MAX_DIAGNOSTICS = 25
MAX_CHUNK_CHARS = 6000


@dataclass(frozen=True)
class CargoRunResult:
    """A captured cargo run — command + environment + transcript + exit code. Pure
    record; no interpretation."""

    command: tuple[str, ...]
    cwd: str
    rustc_version: str
    cargo_version: str
    target_triple: str
    exit_code: int
    transcript: str


def _first_line(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        text = p.stdout or p.stderr
        return text.strip().splitlines()[0] if text.strip() else ""
    except Exception:  # noqa: BLE001 — env capture is best-effort
        return ""


def _target_triple() -> str:
    try:
        p = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, timeout=20)
        for line in p.stdout.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def run_cargo(
    project_dir: str, subcommand: str = "check", *, timeout: int = 600
) -> CargoRunResult:
    """Run `cargo <subcommand>` in ``project_dir``, capturing env + transcript. The
    live seam (subprocess); not exercised by unit tests. ``cargo check/build/test``
    do not mutate source (build/test write only to ``target/``)."""
    cmd = ["cargo", subcommand]
    try:
        p = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=timeout
        )
        rc, transcript = p.returncode, (p.stdout + p.stderr)
    except FileNotFoundError:
        rc, transcript = 127, "cargo not found on PATH"
    except subprocess.TimeoutExpired:
        rc, transcript = 124, f"cargo {subcommand} timed out after {timeout}s"
    return CargoRunResult(
        command=tuple(cmd),
        cwd=project_dir,
        rustc_version=_first_line(["rustc", "--version"]),
        cargo_version=_first_line(["cargo", "--version"]),
        target_triple=_target_triple(),
        exit_code=rc,
        transcript=transcript,
    )


_DIAG_BOUNDARY = re.compile(r"^(error(\[E\d+\])?|warning):", re.MULTILINE)


def split_diagnostics(
    transcript: str,
    *,
    max_diagnostics: int = MAX_DIAGNOSTICS,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> list[str]:
    """Split rustc/cargo output into per-diagnostic chunks. Each chunk starts at an
    ``error`` / ``error[Exxxx]`` / ``warning:`` line and runs to the next boundary. If
    there are no such boundaries (e.g. a test-failure transcript), the whole transcript
    is a single chunk. Bounded in count and per-chunk size."""
    starts = [m.start() for m in _DIAG_BOUNDARY.finditer(transcript)]
    if not starts:
        return [transcript[:max_chunk_chars]] if transcript.strip() else []
    chunks: list[str] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(transcript)
        chunk = transcript[s:e].strip()
        if chunk:
            chunks.append(chunk[:max_chunk_chars])
        if len(chunks) >= max_diagnostics:
            break
    return chunks


@dataclass(frozen=True)
class CargoTriageReport:
    """The aggregate result: the cargo run + a non-authoritative candidate receipt per
    diagnostic. ``truncated`` is True if more diagnostics existed than were triaged."""

    cargo: CargoRunResult
    diagnostics_found: int
    receipts: tuple[LocalCandidateReceipt, ...]
    truncated: bool

    @property
    def observed(self) -> int:
        return sum(1 for r in self.receipts if r.is_observed)


def triage_cargo_result(
    cargo: CargoRunResult,
    *,
    model: str,
    client: LocalModelClient,
    receipt_sink: Any | None = None,
    max_diagnostics: int = MAX_DIAGNOSTICS,
) -> CargoTriageReport:
    """Pure orchestration over a captured cargo run: split diagnostics, triage each
    through the existing failure_triage worker, aggregate. A clean run (exit 0) yields
    no diagnostics and no receipts."""
    if cargo.exit_code == 0:
        return CargoTriageReport(cargo, 0, (), False)
    all_chunks = split_diagnostics(cargo.transcript, max_diagnostics=10**9)
    chunks = all_chunks[:max_diagnostics]
    receipts = []
    for idx, chunk in enumerate(chunks):
        req = LocalCandidateRequest(
            task_kind=TASK_FAILURE_TRIAGE,
            model=model,
            command=" ".join(cargo.command) + f" [diag {idx + 1}/{len(chunks)}]",
            exit_code=cargo.exit_code,
            transcript=chunk,
        )
        receipts.append(triage_failure(req, client=client, receipt_sink=receipt_sink))
    return CargoTriageReport(
        cargo=cargo,
        diagnostics_found=len(all_chunks),
        receipts=tuple(receipts),
        truncated=len(all_chunks) > len(chunks),
    )


def triage_cargo_project(
    project_dir: str,
    subcommand: str = "check",
    *,
    model: str,
    client: LocalModelClient,
    timeout: int = 600,
    receipt_sink: Any | None = None,
) -> CargoTriageReport:
    """Live entry: run cargo, then triage the diagnostics. On-prem / frontier-free
    when ``client`` is a local Ollama client. The operator points this at a tree
    (incl. a secret NQ mac port) and runs it locally."""
    cargo = run_cargo(project_dir, subcommand, timeout=timeout)
    return triage_cargo_result(
        cargo, model=model, client=client, receipt_sink=receipt_sink
    )


__all__ = [
    "MAX_DIAGNOSTICS",
    "MAX_CHUNK_CHARS",
    "CargoRunResult",
    "run_cargo",
    "split_diagnostics",
    "CargoTriageReport",
    "triage_cargo_result",
    "triage_cargo_project",
]
