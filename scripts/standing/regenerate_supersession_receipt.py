#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the prior-validator validation receipt for a successor
bootstrap declaration.

Per ratified Q4 + ``decision.validator.v0_1_0``, every validator
version after v0.1.0 is admissible only if a validation receipt
produced by the *prior* validator targets it. The receipt is a
content-addressed JSON artifact stored next to the successor
declaration. This script (re)mints that artifact deterministically.

Usage::

    python scripts/standing/regenerate_supersession_receipt.py \\
        docs/doctrine/decisions/validator-v0_2_0.md

The script:

1. Reads the successor declaration's frontmatter to find:
   - ``policy_artifact_id`` (the successor's id)
   - ``supersedes`` (the prior version's id)
   - ``prior_validation_receipt_path`` (relative output path)
2. Hashes the successor declaration file → ``successor_content_hash``
3. Loads the prior declaration to extract:
   - ``validator_version`` (e.g. "0.1.0")
   - ``expected_ruleset_hash`` (the prior validator's ruleset hash)
4. Builds a structurally complete :class:`ValidationReceipt`-shaped
   dict with ``outcome=VALID`` and ``target_receipts=[{id,
   content_hash}]`` pointing at the successor declaration
5. Writes canonical JSON to the path declared in successor frontmatter

The output is byte-deterministic: same inputs produce the same bytes.
Re-running with no input changes is a no-op against the file system
(content_hash unchanged).

When to re-run:
- Successor declaration's content changed (any byte edit). The
  declaration's content_hash changed, so the receipt's
  ``target_receipts`` must be updated to match.
- Prior declaration's metadata changed. Should be rare — ratified
  declarations are immutable. If it happens (e.g. typo fix), the
  receipt's ``ruleset_hash`` or ``validator_version`` may need to
  match the new value.

What this script does NOT do:
- Run the prior validator's logic. The receipt is a structural
  attestation; the actual checks the prior validator would have
  performed (well-formed policy_declaration shape, supersedes
  pointing back, etc.) are the operator's responsibility before
  invoking this script.
- Verify ratification status. The script will happily produce a
  receipt for a candidate declaration. Ratification is a separate
  step.
- Sign the receipt cryptographically. Tamper-evidence comes from
  the receipt's ``target_receipts.content_hash`` binding the
  successor declaration's bytes; if either is altered, the
  validator's startup check fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs" / "receipt_kernel" / "src"))

from governor.standing.policy_registry import (  # noqa: E402
    load_decisions_directory,
)
from governor.standing.types import canonical_json  # noqa: E402


def _file_content_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def regenerate(successor_path: Path, *, validated_at: str | None = None) -> Path:
    decisions_dir = successor_path.parent
    registry = load_decisions_directory(decisions_dir)

    # Locate the successor (it may or may not be ratified yet — we
    # parse its frontmatter directly so this works pre-ratification).
    fm = _read_frontmatter(successor_path)
    successor_id = fm.get("policy_artifact_id")
    prior_id = fm.get("supersedes")
    receipt_relpath = fm.get("prior_validation_receipt_path")
    if not successor_id or not prior_id or not receipt_relpath:
        raise SystemExit(
            f"successor declaration {successor_path.name} must declare "
            "policy_artifact_id, supersedes, and prior_validation_receipt_path"
        )
    prior = registry.get(prior_id)
    if prior is None:
        raise SystemExit(
            f"prior declaration {prior_id!r} not found in {decisions_dir}; "
            "ratify it before regenerating the successor's receipt"
        )

    successor_content_hash = _file_content_hash(successor_path)
    prior_version = prior.frontmatter.get("validator_version")
    prior_ruleset_hash = prior.frontmatter.get("expected_ruleset_hash")
    if not prior_version or not prior_ruleset_hash:
        raise SystemExit(
            f"prior declaration {prior_id!r} missing validator_version or "
            "expected_ruleset_hash in frontmatter"
        )

    receipt = {
        "validator_id": "agent_gov.standing_chain_validator",
        "validator_version": prior_version,
        "ruleset_hash": prior_ruleset_hash,
        "policy_registry_hash": registry.registry_hash(),
        "validated_at": validated_at
        or datetime.now(timezone.utc).isoformat(),
        "target_receipts": [
            {"id": successor_id, "content_hash": successor_content_hash}
        ],
        "outcome": "VALID",
        "violations": [],
        "exceptions": [],
    }

    out_path = decisions_dir / receipt_relpath
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(canonical_json(receipt))
    return out_path


def _read_frontmatter(path: Path) -> dict[str, str | None]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{path} has no frontmatter block")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SystemExit(f"{path} has no closing frontmatter delimiter")
    fm: dict[str, str | None] = {}
    for line in text[4:end].splitlines():
        line = line.rstrip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value in ("", "null"):
            fm[key] = None
        else:
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            fm[key] = value
    return fm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "successor_declaration",
        type=Path,
        help="Path to the successor bootstrap declaration .md file",
    )
    parser.add_argument(
        "--validated-at",
        default=None,
        help="Override timestamp (ISO 8601 UTC). Default: now. "
        "Set to a fixed value for byte-deterministic regeneration.",
    )
    args = parser.parse_args()
    out_path = regenerate(
        args.successor_declaration, validated_at=args.validated_at
    )
    rel = out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path
    print(f"wrote {rel}")
    print(f"  size: {out_path.stat().st_size} bytes")
    print(f"  sha256: {_file_content_hash(out_path)}")


if __name__ == "__main__":
    main()
