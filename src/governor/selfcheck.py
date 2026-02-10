"""
Self-check: automated deployment health verification.

Validates governor store integrity — receipt stores, exception records,
pending violations, directory structure, and cross-references.

Usage:
    governor selfcheck          # Fast: store integrity only
    governor selfcheck --full   # Full: adds cross-ledger consistency
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CheckItem:
    """A single self-check result."""

    name: str
    status: str   # "ok" | "warn" | "fail"
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def run_selfcheck(gov_dir: Path, scope: str = "fast") -> list[CheckItem]:
    """Run self-check and return results.

    Args:
        gov_dir: Path to .governor directory
        scope: "fast" for store integrity only, "full" for cross-ledger checks

    Returns:
        List of CheckItem results
    """
    items: list[CheckItem] = []

    items.append(_check_dir_structure(gov_dir))
    items.append(_check_receipt_store(gov_dir))
    items.append(_check_exception_records(gov_dir))
    items.append(_check_pending_violation(gov_dir))
    items.append(_check_unlinked_exceptions(gov_dir))

    if scope == "full":
        items.append(_check_evidence_blobs(gov_dir))
        items.append(_check_receipt_exception_xrefs(gov_dir))

    return items


def _check_dir_structure(gov_dir: Path) -> CheckItem:
    """Check that required governor directories exist."""
    if not gov_dir.exists():
        return CheckItem("dir_structure", "fail", f"{gov_dir} does not exist")

    required = ["gate_receipts", "evidence"]
    missing = [d for d in required if not (gov_dir / d).exists()]

    if missing:
        return CheckItem(
            "dir_structure", "warn", f"Missing dirs: {', '.join(missing)}"
        )
    return CheckItem("dir_structure", "ok", "All required directories present")


def _check_receipt_store(gov_dir: Path) -> CheckItem:
    """Check that receipt JSONL files parse cleanly."""
    receipts_dir = gov_dir / "gate_receipts"
    if not receipts_dir.exists():
        return CheckItem("receipt_store", "ok", "No receipt store yet")

    total = 0
    errors = 0
    for jsonl_file in receipts_dir.glob("*.jsonl"):
        try:
            for line_no, line in enumerate(jsonl_file.read_text().splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    errors += 1
        except OSError:
            errors += 1

    if errors:
        return CheckItem(
            "receipt_store", "warn",
            f"{errors} parse error(s) in {total} receipt(s)"
        )
    return CheckItem("receipt_store", "ok", f"{total} receipt(s), all valid")


def _check_exception_records(gov_dir: Path) -> CheckItem:
    """Check that exception JSON files parse cleanly."""
    exc_dir = gov_dir / "exceptions"
    if not exc_dir.exists():
        return CheckItem("exception_records", "ok", "No exceptions directory")

    total = 0
    errors = 0
    for f in exc_dir.glob("*.json"):
        total += 1
        try:
            data = json.loads(f.read_text())
            # Minimal shape check
            if "id" not in data or "violations" not in data:
                errors += 1
        except (json.JSONDecodeError, OSError):
            errors += 1

    if errors:
        return CheckItem(
            "exception_records", "warn",
            f"{errors} invalid file(s) in {total} exception(s)"
        )
    return CheckItem("exception_records", "ok", f"{total} exception(s), all valid")


def _check_pending_violation(gov_dir: Path) -> CheckItem:
    """Check for stale pending violation files."""
    pending_path = gov_dir / "pending_violations.json"
    if not pending_path.exists():
        return CheckItem("pending_violation", "ok", "No pending violation")

    try:
        data = json.loads(pending_path.read_text())
        if not data:
            return CheckItem("pending_violation", "ok", "Pending file empty")
        status = data.get("status", "pending")
        if status == "pending":
            pending_id = data.get("id", "unknown")
            return CheckItem(
                "pending_violation", "warn",
                f"Stale pending violation: {pending_id}"
            )
        return CheckItem("pending_violation", "ok", f"Pending resolved ({status})")
    except (json.JSONDecodeError, OSError):
        return CheckItem("pending_violation", "warn", "Pending file corrupt")


def _check_unlinked_exceptions(gov_dir: Path) -> CheckItem:
    """Canary: exceptions with receipt_id=None indicate receipt emit failures.

    Any exception created by resolve_proceed should carry the receipt_id of
    the block receipt that triggered it. Missing receipt_ids mean the receipt
    system failed silently during the block — audit linkage is degraded.
    """
    exc_dir = gov_dir / "exceptions"
    if not exc_dir.exists():
        return CheckItem("unlinked_exceptions", "ok", "No exceptions to check")

    total = 0
    unlinked = 0
    for f in exc_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if "id" in data:
                total += 1
                if data.get("receipt_id") is None:
                    unlinked += 1
        except (json.JSONDecodeError, OSError):
            continue

    if not total:
        return CheckItem("unlinked_exceptions", "ok", "No exceptions to check")

    if unlinked:
        return CheckItem(
            "unlinked_exceptions", "warn",
            f"{unlinked}/{total} exception(s) missing receipt_id"
            " — receipt emit may have failed during block"
        )
    return CheckItem(
        "unlinked_exceptions", "ok",
        f"{total} exception(s), all linked to receipts"
    )


def _check_evidence_blobs(gov_dir: Path) -> CheckItem:
    """Check that every receipt has a matching evidence blob (full scope)."""
    receipts_dir = gov_dir / "gate_receipts"
    evidence_dir = gov_dir / "evidence"

    if not receipts_dir.exists():
        return CheckItem("evidence_blobs", "ok", "No receipts to check")

    total = 0
    missing = 0
    for jsonl_file in receipts_dir.glob("*.jsonl"):
        for line in jsonl_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                receipt = json.loads(line)
                evidence_hash = receipt.get("evidence_hash", "")
                if evidence_hash:
                    total += 1
                    # Evidence is sharded by hash[:2]
                    shard = evidence_hash[:2]
                    blob_path = evidence_dir / shard / f"{evidence_hash}.json"
                    if not blob_path.exists():
                        missing += 1
            except json.JSONDecodeError:
                continue

    if missing:
        return CheckItem(
            "evidence_blobs", "warn",
            f"{missing} missing evidence blob(s) out of {total} receipt(s)"
        )
    return CheckItem("evidence_blobs", "ok", f"{total} evidence blob(s), all present")


def _check_receipt_exception_xrefs(gov_dir: Path) -> CheckItem:
    """Check that exception receipt_ids point to valid receipts (full scope)."""
    exc_dir = gov_dir / "exceptions"
    if not exc_dir.exists():
        return CheckItem("receipt_exception_xrefs", "ok", "No exceptions to check")

    # Build receipt ID set
    receipt_ids: set[str] = set()
    receipts_dir = gov_dir / "gate_receipts"
    if receipts_dir.exists():
        for jsonl_file in receipts_dir.glob("*.jsonl"):
            for line in jsonl_file.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    receipt = json.loads(line)
                    rid = receipt.get("receipt_id", "")
                    if rid:
                        receipt_ids.add(rid)
                except json.JSONDecodeError:
                    continue

    total = 0
    orphans = 0
    for f in exc_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            rid = data.get("receipt_id")
            if rid is not None:
                total += 1
                if rid not in receipt_ids:
                    orphans += 1
        except (json.JSONDecodeError, OSError):
            continue

    if orphans:
        return CheckItem(
            "receipt_exception_xrefs", "warn",
            f"{orphans} orphan receipt ref(s) out of {total} linked exception(s)"
        )
    detail = f"{total} linked exception(s), all valid" if total else "No linked exceptions"
    return CheckItem("receipt_exception_xrefs", "ok", detail)
