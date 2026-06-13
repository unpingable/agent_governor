"""Control baselines — named, admitted rollback targets (P2.2; registry only).

Workflow-kernel campaign, Phase 2
(`specs/gaps/GOV_GAP_CONTROL_BASELINE_001.md`). A ``ControlBaseline`` is the
*admitted rollback target* an annealing delta must name. This slice is the TYPE
plus a record registry — no activation, no rollback execution, no config write
(those are Phase 3).

The hard red line (`docs/doctrine/annealing_and_recomposition.md` §4):

> Checkpoints/forks/promotions are resumability/continuity machinery unless
> explicitly admitted as control-plane baselines. A promoted session state is
> not automatically a known-good policy baseline.

Enforced mechanically here: a ControlBaseline exists ONLY via
:func:`admit_baseline`, which requires a ``creation_receipt_id`` — there is no
auto-mint. This module does not import ``session_continuity``; it stores a
``checkpoint_ref`` *string* (a reference to a continuity checkpoint), never a
live session, and nothing in the session-promotion path can reach baseline
creation. Same/other "baseline" senses are kept distinct: ``BaselineProfile``
(auto_tuning, a metric snapshot) is NOT this.

Authority classification (loop §11.3): the registry writes baseline RECORDS to a
dedicated dir — record-keeping, like ReceiptStore/ProposalStore, NOT a
config-write or apply path. No method here applies, activates, or rolls back.
Reuses ``gate_receipt`` canonicalization (no second canonicalization).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gate_receipt import canonical_json, content_hash

_BASELINE_DIRNAME = "control_baselines"


@dataclass(frozen=True)
class ControlBaseline:
    """A named, admitted rollback target.

    Identity (``baseline_id``) is content-addressed over the rollback target
    itself — name, config hashes, checkpoint reference, lineage — NOT the
    admission metadata (``creation_receipt_id`` / ``admitted_by`` are metadata,
    like a receipt's timestamp). So two admissions of identical config content
    share a baseline_id, and any two baselines are diffable from their config
    hashes alone (bisectability).
    """

    name: str
    config_hashes: tuple[tuple[str, str], ...]  # sorted (config_key, hash) pairs
    creation_receipt_id: str  # admission receipt — mandatory, no auto-mint
    checkpoint_ref: str | None = None  # session_continuity Checkpoint id (ref only)
    supersedes: str | None = None  # prior baseline_id (lineage pointer)
    admitted_by: str = ""

    def __post_init__(self) -> None:
        # Canonicalize config_hashes ON THE TYPE (not just the factory), so
        # baseline_id is order-independent on EVERY construction path — direct
        # construction and from_dict included. Identical content -> identical id.
        object.__setattr__(
            self, "config_hashes", tuple(sorted(self.config_hashes))
        )
        if not self.name:
            raise ValueError("name must be non-empty")
        if not self.creation_receipt_id:
            raise ValueError(
                "creation_receipt_id is mandatory — a ControlBaseline exists "
                "only via explicit admission, never auto-minted from a session "
                "promotion or any other path"
            )
        if not self.admitted_by:
            raise ValueError("admitted_by is mandatory")

    def identity_dict(self) -> dict[str, Any]:
        return {
            "schema": "control_baseline_v0",
            "name": self.name,
            "config_hashes": [list(pair) for pair in self.config_hashes],
            "checkpoint_ref": self.checkpoint_ref,
            "supersedes": self.supersedes,
        }

    @property
    def baseline_id(self) -> str:
        return content_hash(canonical_json(self.identity_dict()))

    def to_dict(self) -> dict[str, Any]:
        payload = self.identity_dict()
        payload["baseline_id"] = self.baseline_id
        payload["creation_receipt_id"] = self.creation_receipt_id
        payload["admitted_by"] = self.admitted_by
        return payload

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ControlBaseline:
        return cls(
            name=d["name"],
            config_hashes=tuple(tuple(p) for p in d.get("config_hashes", [])),
            creation_receipt_id=d["creation_receipt_id"],
            checkpoint_ref=d.get("checkpoint_ref"),
            supersedes=d.get("supersedes"),
            admitted_by=d.get("admitted_by", ""),
        )


def admit_baseline(
    *,
    name: str,
    config_hashes: Mapping[str, str] | tuple[tuple[str, str], ...],
    creation_receipt_id: str,
    admitted_by: str,
    checkpoint_ref: str | None = None,
    supersedes: str | None = None,
) -> ControlBaseline:
    """Admit a baseline. ``creation_receipt_id`` is REQUIRED — the only way to
    mint one. Nothing derives a baseline from a session promotion (the red line):
    admission is an explicit, receipted act."""
    # Convert a Mapping to pairs; ControlBaseline.__post_init__ does the
    # canonical sort, so identity is order-independent regardless of this path.
    if isinstance(config_hashes, Mapping):
        normalized = tuple(config_hashes.items())
    else:
        normalized = tuple(config_hashes)
    return ControlBaseline(
        name=name,
        config_hashes=normalized,
        creation_receipt_id=creation_receipt_id,
        admitted_by=admitted_by,
        checkpoint_ref=checkpoint_ref,
        supersedes=supersedes,
    )


class ControlBaselineStore:
    """File-per-item record store under ``<root>/control_baselines/``.

    Writes baseline RECORDS only — never config, never applies/activates/rolls
    back. No delete in this slice (deletion + reference-counting is Phase 3a,
    once activated deltas can reference a baseline).
    """

    def __init__(self, root: Path | str):
        self._dir = Path(root) / _BASELINE_DIRNAME

    @property
    def directory(self) -> Path:
        return self._dir

    def put(self, baseline: ControlBaseline) -> Path:
        """Persist a baseline record (atomic temp+rename). Returns its path."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{baseline.baseline_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(baseline.to_dict(), sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def get(self, baseline_id: str) -> ControlBaseline | None:
        path = self._dir / f"{baseline_id}.json"
        if not path.exists():
            return None
        return ControlBaseline.from_dict(json.loads(path.read_text()))

    def list_ids(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json"))
