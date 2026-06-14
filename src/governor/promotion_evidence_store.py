# SPDX-License-Identifier: Apache-2.0
"""P4.0c — the first promotion-evidence producer: persist ``ActivationReceipt``.

The model layer (``promotion_evidence``) is pure and does no IO. This is the IO
seam for exactly ONE receipt type — the chain root, the P3.1 activation. One
producer, one storage layout, one verifier. It does NOT emit live-survival
observations, replay holdouts, or operator basis; it mints no baseline and chooses
no threshold N. Those are later producers.

**Storage layout** (canonical root is ``.governor/``)::

    <root>/promotion_evidence/activations/<trial_key>.json

``trial_key`` is ``sha256(trial_id)`` hex — a filename-safe, deterministic key, so
``get(trial_id)`` recomputes the path without trusting the trial_id as a path
component (no traversal). One activation per trial in this slice.

**Tamper anchor.** Each stored file carries the receipt's ``content_hash``
alongside its identity fields. On load the hash is *recomputed from the fields* and
compared; a file that claims a hash its content does not produce is refused
(``ActivationReceiptTamperError``). The stored ``trial_id`` is also checked against
the requested one (key-collision / swap guard).

What this catches and what it does not: the self-hash refuses a file whose declared
hash disagrees with its content. It does NOT, by itself, detect a *fully* rewritten
but internally-consistent activation — that is caught downstream, where observation
receipts bind to the activation's ``content_hash``: rewriting the activation changes
its hash, so observations bound to the original no longer walk (``promotion_evidence``
walk layer). Provenance hardening beyond self-hash is a later seam, not this one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .gate_receipt import canonical_json, content_hash
from .promotion_evidence import ActivationReceipt

_EVIDENCE_DIRNAME = "promotion_evidence"
_ACTIVATIONS_DIRNAME = "activations"


class ActivationReceiptTamperError(ValueError):
    """A persisted activation receipt failed its integrity check on load: the
    declared ``content_hash`` does not match the hash recomputed from its fields,
    or the stored ``trial_id`` does not match the requested key. Refused, not
    repaired — a tampered receipt is not evidence."""


def _trial_key(trial_id: str) -> str:
    return hashlib.sha256(trial_id.encode("utf-8")).hexdigest()


class ActivationReceiptStore:
    """File-per-trial store for ``ActivationReceipt`` under
    ``<root>/promotion_evidence/activations/``. Atomic writes (temp+rename),
    integrity-checked loads."""

    def __init__(self, root: Path | str):
        self._dir = Path(root) / _EVIDENCE_DIRNAME / _ACTIVATIONS_DIRNAME

    @property
    def directory(self) -> Path:
        return self._dir

    def put(self, receipt: ActivationReceipt) -> Path:
        """Persist an activation receipt (atomic temp+rename). Returns its path."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_trial_key(receipt.trial_id)}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(receipt.to_dict(), sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def get(self, trial_id: str) -> ActivationReceipt | None:
        """Load + integrity-check an activation receipt. Returns ``None`` if no
        receipt exists for the trial (a clean miss — the walk layer treats a
        missing activation as not-walkable). Raises
        :class:`ActivationReceiptTamperError` if a stored file fails its check."""
        path = self._dir / f"{_trial_key(trial_id)}.json"
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        receipt = ActivationReceipt.from_dict(d)

        recomputed = content_hash(canonical_json(receipt.identity_dict()))
        declared = d.get("content_hash")
        if declared != recomputed:
            raise ActivationReceiptTamperError(
                f"activation receipt for trial {trial_id!r} failed integrity check: "
                f"declared content_hash {declared!r} != recomputed {recomputed!r}"
            )
        if receipt.trial_id != trial_id:
            raise ActivationReceiptTamperError(
                f"activation receipt at key for {trial_id!r} carries a different "
                f"trial_id {receipt.trial_id!r} (key collision / swap)"
            )
        return receipt

    def list_trial_keys(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json"))


__all__ = [
    "ActivationReceiptStore",
    "ActivationReceiptTamperError",
]
