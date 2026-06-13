"""Record store for proposed annealing deltas (P2.3).

Kept SEPARATE from ``annealing.py`` on purpose: that module is the delta type +
factory and is fenced write-free (its tests assert no write primitive). Record
persistence — which does write files — lives here, exactly as
``control_baseline.py`` holds ``ControlBaselineStore``.

Authority classification (loop §11.3): this writes proposed-delta RECORDS to a
dedicated dir (``<root>/annealing_deltas/``) — record-keeping, like
ReceiptStore/ControlBaselineStore — NOT a config write and NOT an apply path.
There is no apply / activate / rollback method here; a stored record is a
proposal, never an effect.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .annealing import AnnealingDelta

_DELTA_DIRNAME = "annealing_deltas"
_DELTA_ID_RE = re.compile(r"^[0-9a-f]{64}$")


class AnnealingDeltaStore:
    """File-per-item record store for proposed deltas under
    ``<root>/annealing_deltas/``. Record-keeping only — never config, never
    applies/activates. No delete in this slice."""

    def __init__(self, root: Path | str):
        self._dir = Path(root) / _DELTA_DIRNAME

    @property
    def directory(self) -> Path:
        return self._dir

    def put(self, delta: AnnealingDelta) -> Path:
        """Persist a proposed-delta record (atomic temp+rename). Returns path."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{delta.delta_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(delta.to_dict(), sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def get(self, delta_id: str) -> AnnealingDelta | None:
        # Read-side fence: reject anything that is not a clean content id (closes
        # path traversal like '../x'), and verify the loaded record's recomputed
        # id matches the requested id (a tampered/forged file under a mismatched
        # name does not pass). delta_id is content, never trusted from the file.
        if not _DELTA_ID_RE.match(delta_id):
            return None
        path = self._dir / f"{delta_id}.json"
        if not path.exists():
            return None
        delta = AnnealingDelta.from_dict(json.loads(path.read_text()))
        if delta.delta_id != delta_id:
            return None
        return delta

    def list_ids(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json"))
