# SPDX-License-Identifier: Apache-2.0
"""
CI Lane: receipt-producing command wrapper and policy verifier.

Thin glue that makes governor receipts *required* in CI pipelines.
``ci_wrap()`` runs a command and emits a self-contained receipt bundle.
``ci_verify()`` checks that all required receipts exist and pass policy.

Self-contained bundles (evidence inlined alongside receipt) so they are
portable — unlike ``.governor/`` receipts where evidence lives in a
separate store.
"""

from __future__ import annotations

import json
import os
import platform
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gate_receipt import (
    GateReceipt,
    canonical_json,
    content_hash,
    create_receipt,
    make_timing,
)

# =============================================================================
# Constants
# =============================================================================

CI_WRAP_GATE = "ci_wrap"
CI_VERIFY_GATE = "ci_verify"

_MAX_CAPTURE_BYTES = 10 * 1024 * 1024  # 10 MB stdout/stderr cap

VALID_CI_KINDS: frozenset[str] = frozenset({
    "unit_tests",
    "lint",
    "typecheck",
    "build",
    "security_scan",
    "integration_tests",
    "e2e_tests",
    "coverage",
})


# =============================================================================
# Helpers
# =============================================================================


def _utc_now() -> str:
    """UTC ISO-8601 with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# =============================================================================
# GitState
# =============================================================================


@dataclass(frozen=True)
class GitState:
    sha: str    # "" if not in a git repo
    dirty: bool  # True if uncommitted changes or untracked files

    def to_dict(self) -> dict[str, Any]:
        return {"sha": self.sha, "dirty": self.dirty}


def capture_git_state(cwd: Path | None = None) -> GitState:
    """Capture current git SHA and dirty status.  Never raises."""
    sha = ""
    dirty = False
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=str(cwd) if cwd else None,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
            cwd=str(cwd) if cwd else None,
        )
        if result.returncode == 0 and result.stdout.strip():
            dirty = True
    except Exception:
        pass

    return GitState(sha=sha, dirty=dirty)


# =============================================================================
# CiReceiptBundle
# =============================================================================


@dataclass(frozen=True)
class CiReceiptBundle:
    """Self-contained receipt + evidence for CI portability."""
    receipt: GateReceipt
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"receipt": self.receipt.to_dict(), "evidence": self.evidence}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CiReceiptBundle:
        return cls(
            receipt=GateReceipt.from_dict(d["receipt"]),
            evidence=d["evidence"],
        )


# =============================================================================
# ci_wrap
# =============================================================================


@dataclass(frozen=True)
class CiWrapResult:
    exit_code: int
    receipt: GateReceipt | None   # None if emission failed (fail-open)
    receipt_path: Path | None     # Where the receipt was written


def _hash_file_capped(path: Path, cap: int) -> tuple[str, bool]:
    """Hash up to *cap* bytes of *path*.  Returns (hex_hash, truncated)."""
    size = path.stat().st_size
    truncated = size > cap
    with open(path, "rb") as f:
        data = f.read(cap)
    return content_hash(data), truncated


def _write_bundle(bundle: CiReceiptBundle, receipt_out: Path) -> Path:
    """Write bundle to the path indicated by suffix convention.

    - ``.jsonl`` suffix  → append one JSONL line
    - ``.json`` suffix   → write single JSON object
    - no recognised suffix → treat as directory, write individual file
    """
    suffix = receipt_out.suffix.lower()

    if suffix == ".jsonl":
        receipt_out.parent.mkdir(parents=True, exist_ok=True)
        with open(receipt_out, "a") as f:
            f.write(bundle.to_json() + "\n")
            f.flush()
        return receipt_out

    if suffix == ".json":
        receipt_out.parent.mkdir(parents=True, exist_ok=True)
        receipt_out.write_text(bundle.to_json() + "\n")
        return receipt_out

    # Directory mode
    receipt_out.mkdir(parents=True, exist_ok=True)
    kind = bundle.evidence.get("ci_kind", "unknown")
    uid = uuid.uuid4().hex[:8]
    fname = f"ci_wrap_{kind}_{uid}.json"
    out = receipt_out / fname
    out.write_text(bundle.to_json() + "\n")
    return out


def ci_wrap(
    command: list[str],
    ci_kind: str,
    receipt_out: Path,
    *,
    cwd: Path | None = None,
    timestamp: str | None = None,
) -> CiWrapResult:
    """Run *command*, emit a CI receipt bundle.

    Returns CiWrapResult — exit_code is always the child's exit code.
    Receipt emission is fail-open (errors print warning to stderr).
    """
    if ci_kind not in VALID_CI_KINDS:
        raise ValueError(
            f"Invalid ci_kind {ci_kind!r}; "
            f"must be one of {sorted(VALID_CI_KINDS)}"
        )

    git_state = capture_git_state(cwd)
    ts = timestamp or _utc_now()

    # Run command with stdout/stderr to temp files (avoids pipe deadlock)
    stdout_file = None
    stderr_file = None
    try:
        stdout_file = tempfile.NamedTemporaryFile(delete=False, prefix="ci_stdout_")
        stderr_file = tempfile.NamedTemporaryFile(delete=False, prefix="ci_stderr_")
        stdout_path = Path(stdout_file.name)
        stderr_path = Path(stderr_file.name)
        stdout_file.close()
        stderr_file.close()

        start_ns = time.monotonic_ns()
        with open(stdout_path, "wb") as out_f, open(stderr_path, "wb") as err_f:
            result = subprocess.run(
                command,
                stdout=out_f,
                stderr=err_f,
                cwd=str(cwd) if cwd else None,
            )
        end_ns = time.monotonic_ns()
        returncode = result.returncode

        # Hash captured output
        stdout_hash, stdout_truncated = _hash_file_capped(stdout_path, _MAX_CAPTURE_BYTES)
        stderr_hash, stderr_truncated = _hash_file_capped(stderr_path, _MAX_CAPTURE_BYTES)
    finally:
        # Clean up temp files
        for p in (stdout_file, stderr_file):
            if p is not None:
                try:
                    os.unlink(p.name)
                except OSError:
                    pass

    # Build evidence bundle (duration excluded — timing metadata only)
    evidence_bundle: dict[str, Any] = {
        "exit_code": returncode,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "git_sha": git_state.sha,
        "dirty": git_state.dirty,
        "ci_kind": ci_kind,
        "command": command,
        "command_display": shlex.join(command)[:500],
        "python_version": platform.python_version(),
    }

    # Subject uses argv list (not joined string — avoids quoting collisions)
    subject_bytes = canonical_json({
        "ci_kind": ci_kind,
        "command": command,
        "git_sha": git_state.sha,
        "dirty": git_state.dirty,
    })

    verdict = "pass" if returncode == 0 else "block"
    timing = make_timing(start_ns, end_ns)

    try:
        receipt = create_receipt(
            gate=CI_WRAP_GATE,
            verdict=verdict,
            subject_kind="ci_wrap",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"ci_kind": ci_kind},
            timestamp=ts,
            timing=timing,
        )
        bundle = CiReceiptBundle(receipt=receipt, evidence=evidence_bundle)
        written_path = _write_bundle(bundle, receipt_out)
        return CiWrapResult(exit_code=returncode, receipt=receipt, receipt_path=written_path)
    except Exception as exc:
        print(
            f"WARNING: receipt emission failed: {exc}; policy may block later",
            file=sys.stderr,
        )
        return CiWrapResult(exit_code=returncode, receipt=None, receipt_path=None)


# =============================================================================
# load_ci_receipts
# =============================================================================


def load_ci_receipts(path: Path) -> list[CiReceiptBundle]:
    """Load CI receipt bundles from a file or directory.

    - File (.jsonl): one bundle per line
    - Directory: glob ``*.json`` + ``*.jsonl``
    - Filters to ``gate == CI_WRAP_GATE`` (ignores ci_verify meta-receipts)
    - Skips malformed entries (warns to stderr)
    - Returns sorted by receipt timestamp
    """
    bundles: list[CiReceiptBundle] = []

    def _load_jsonl(p: Path) -> None:
        for lineno, line in enumerate(p.read_text().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                b = CiReceiptBundle.from_dict(d)
                if b.receipt.gate == CI_WRAP_GATE:
                    bundles.append(b)
            except Exception as exc:
                print(f"WARNING: skipping malformed entry in {p}:{lineno}: {exc}", file=sys.stderr)

    def _load_json(p: Path) -> None:
        try:
            d = json.loads(p.read_text())
            b = CiReceiptBundle.from_dict(d)
            if b.receipt.gate == CI_WRAP_GATE:
                bundles.append(b)
        except Exception as exc:
            print(f"WARNING: skipping malformed file {p}: {exc}", file=sys.stderr)

    if path.is_dir():
        for f in sorted(path.iterdir()):
            if f.suffix == ".jsonl":
                _load_jsonl(f)
            elif f.suffix == ".json":
                _load_json(f)
    elif path.suffix == ".jsonl":
        _load_jsonl(path)
    else:
        _load_json(path)

    # Sort by timestamp (canonical Z-suffix makes string sort correct)
    bundles.sort(key=lambda b: b.receipt.timestamp)
    return bundles


# =============================================================================
# CiPolicy + ci_verify
# =============================================================================


@dataclass(frozen=True)
class CiPolicy:
    required_kinds: frozenset[str]
    require_clean: bool = True
    require_same_sha: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_kinds": sorted(self.required_kinds),
            "require_clean": self.require_clean,
            "require_same_sha": self.require_same_sha,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CiPolicy:
        return cls(
            required_kinds=frozenset(d.get("required_kinds", [])),
            require_clean=d.get("require_clean", True),
            require_same_sha=d.get("require_same_sha", True),
        )


@dataclass(frozen=True)
class CiVerifyResult:
    ok: bool
    verdict: str                    # "pass" or "block"
    receipt: GateReceipt | None
    checks: dict[str, bool]
    errors: list[str]
    receipts_loaded: int
    kinds_found: list[str]
    git_sha: str | None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ok": self.ok,
            "verdict": self.verdict,
            "checks": self.checks,
            "errors": self.errors,
            "receipts_loaded": self.receipts_loaded,
            "kinds_found": self.kinds_found,
            "git_sha": self.git_sha,
        }
        if self.receipt is not None:
            d["receipt"] = self.receipt.to_dict()
        return d


def ci_verify(
    receipt_path: Path,
    policy: CiPolicy | None = None,
    *,
    receipt_out: Path | None = None,
    timestamp: str | None = None,
) -> CiVerifyResult:
    """Verify CI receipts against policy.

    Returns CiVerifyResult with detailed check outcomes.
    Exit codes: 0 = PASS, 1 = BLOCK, 2 = internal error.
    """
    if policy is None:
        policy = CiPolicy(required_kinds=frozenset())

    ts = timestamp or _utc_now()
    bundles = load_ci_receipts(receipt_path)

    checks: dict[str, bool] = {}
    errors: list[str] = []

    # 1. receipts_loaded — at least one receipt
    checks["receipts_loaded"] = len(bundles) > 0
    if not checks["receipts_loaded"]:
        errors.append("No CI receipts found")

    # Collect kinds and SHAs
    kinds_found: list[str] = []
    shas: list[str] = []
    for b in bundles:
        kind = b.evidence.get("ci_kind", "")
        if kind and kind not in kinds_found:
            kinds_found.append(kind)
        sha = b.evidence.get("git_sha", "")
        shas.append(sha)

    # 2. required_kinds_present
    if policy.required_kinds:
        found_set = frozenset(kinds_found)
        missing = policy.required_kinds - found_set
        checks["required_kinds_present"] = len(missing) == 0
        for k in sorted(missing):
            errors.append(f"Missing required kind: {k}")
    else:
        checks["required_kinds_present"] = True

    # 3. all_pass — every receipt has verdict == "pass"
    all_pass = all(b.receipt.verdict == "pass" for b in bundles) if bundles else True
    checks["all_pass"] = all_pass
    for b in bundles:
        if b.receipt.verdict != "pass":
            errors.append(f"Receipt {b.receipt.receipt_id[:12]} has verdict={b.receipt.verdict}")

    # 4. sha_known — all git_sha values non-empty
    if policy.require_same_sha:
        sha_known = all(s != "" for s in shas) if shas else True
        checks["sha_known"] = sha_known
        for b in bundles:
            if b.evidence.get("git_sha", "") == "":
                errors.append(f"git_sha missing in receipt {b.receipt.receipt_id[:12]} (require_same_sha is on)")
    else:
        checks["sha_known"] = True

    # 5. same_sha — all non-empty git_sha values match
    if policy.require_same_sha:
        non_empty_shas = [s for s in shas if s]
        if len(non_empty_shas) > 1:
            same = all(s == non_empty_shas[0] for s in non_empty_shas)
            checks["same_sha"] = same
            if not same:
                unique = sorted(set(non_empty_shas))
                errors.append(f"git_sha mismatch: {', '.join(s[:12] for s in unique)}")
        else:
            checks["same_sha"] = True
    else:
        checks["same_sha"] = True

    # 6. clean — no receipt has dirty=True
    if policy.require_clean:
        clean = True
        for b in bundles:
            dirty = b.evidence.get("dirty")
            if dirty is None:
                clean = False
                errors.append(f"dirty flag missing in receipt {b.receipt.receipt_id[:12]}")
            elif dirty:
                clean = False
                errors.append(f"Receipt {b.receipt.receipt_id[:12]} has dirty=True")
        checks["clean"] = clean
    else:
        checks["clean"] = True

    # 7. no_conflicting_ids — duplicate IDs OK if bundles are byte-identical
    if bundles:
        by_id: dict[str, str] = {}  # receipt_id -> canonical json of bundle
        conflicting = False
        for b in bundles:
            rid = b.receipt.receipt_id
            bundle_json = json.dumps(b.to_dict(), sort_keys=True)
            if rid in by_id:
                if by_id[rid] != bundle_json:
                    conflicting = True
                    errors.append(f"Conflicting receipt ID: {rid[:12]}")
            else:
                by_id[rid] = bundle_json
        checks["no_conflicting_ids"] = not conflicting
    else:
        checks["no_conflicting_ids"] = True

    # Overall verdict
    ok = all(checks.values())
    verdict = "pass" if ok else "block"

    # Determine canonical SHA
    non_empty = [s for s in shas if s]
    git_sha = non_empty[0] if non_empty else None

    # Build meta-receipt
    meta_receipt: GateReceipt | None = None
    verify_evidence: dict[str, Any] = {
        "checks": checks,
        "errors": errors,
        "receipts_loaded": len(bundles),
        "kinds_found": kinds_found,
        "git_sha": git_sha,
        "policy": policy.to_dict(),
    }
    try:
        meta_receipt = create_receipt(
            gate=CI_VERIFY_GATE,
            verdict=verdict,
            subject_kind="ci_verify",
            subject_bytes=canonical_json(verify_evidence),
            evidence_bundle=verify_evidence,
            gate_config=policy.to_dict(),
            timestamp=ts,
        )
        if receipt_out is not None:
            meta_bundle = CiReceiptBundle(receipt=meta_receipt, evidence=verify_evidence)
            _write_bundle(meta_bundle, receipt_out)
    except Exception as exc:
        print(f"WARNING: ci_verify meta-receipt emission failed: {exc}", file=sys.stderr)

    return CiVerifyResult(
        ok=ok,
        verdict=verdict,
        receipt=meta_receipt,
        checks=checks,
        errors=errors,
        receipts_loaded=len(bundles),
        kinds_found=kinds_found,
        git_sha=git_sha,
    )
