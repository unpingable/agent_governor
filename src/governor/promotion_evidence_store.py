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
from .observation_admissibility import (
    ObservationFacts,
    SurvivalBound,
    derive_in_bounds,
)
from .clock_witness import MonotonicReading
from .operator_basis import OperatorBasisFacts, derive_operator_basis_present
from .promotion_evidence import (
    ActivationReceipt,
    LiveSurvivalObservationReceipt,
    OperatorBasisReceipt,
    ReplayHoldoutReceipt,
)
from .replay_holdout import ReplayHoldoutFacts, derive_replay_verdict

_EVIDENCE_DIRNAME = "promotion_evidence"
_ACTIVATIONS_DIRNAME = "activations"
_OBSERVATIONS_DIRNAME = "observations"
_REPLAY_HOLDOUTS_DIRNAME = "replay_holdouts"


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


class ObservationReceiptTamperError(ValueError):
    """A persisted live-survival observation failed its integrity check on load:
    the declared ``content_hash`` does not match the hash recomputed from its
    inputs, the stored ``trial_id`` does not match the requested key, OR the stored
    ``in_bounds`` conclusion does not match the value re-derived from the stored
    facts + bound. The last is the load-bearing one: **producer-derived is not
    producer-trusted** — the evaluator recomputes the conclusion on load and
    refuses a receipt whose stored conclusion was tampered (e.g. a tripped
    observation re-stamped ``in_bounds: true``)."""


_OBSERVATION_SCHEMA = "promotion_observation_v0"


class ObservationReceiptStore:
    """File-per-observation store under
    ``<root>/promotion_evidence/observations/<trial_key>/<observation_id>.json``.

    The producer COMPUTES ``in_bounds`` (via ``derive_in_bounds``) and persists the
    raw inputs (facts + bound + activation binding) alongside the derived
    conclusion. ``content_hash`` covers the INPUTS only, never the conclusion. On
    ``load_for_trial`` the evaluator: (1) recomputes ``content_hash`` over the
    inputs and refuses a mismatch; (2) checks the stored ``trial_id``; (3)
    **re-derives ``in_bounds`` from the stored facts+bound and refuses if it
    disagrees with the stored conclusion**; then emits a plain
    ``LiveSurvivalObservationReceipt`` (carrying the RE-DERIVED ``in_bounds``) for
    the existing walk/assembler — which independently enforces activation binding,
    trial match, and freshness. The store never trusts the stored conclusion.

    Deriving uses no ``expected_basis`` (deterministic on load); clock attribution
    is handled by the assembler's binding + freshness checks.
    """

    def __init__(self, root: Path | str):
        self._dir = Path(root) / _EVIDENCE_DIRNAME / _OBSERVATIONS_DIRNAME

    @property
    def directory(self) -> Path:
        return self._dir

    def _identity_dict(
        self,
        *,
        observation_id: str,
        facts: ObservationFacts,
        bound: SurvivalBound,
        activation_receipt_hash: str,
    ) -> dict:
        # Identity = INPUTS only. The derived in_bounds/reasons are NOT part of it,
        # so a stored conclusion can be cross-checked by re-derivation independently
        # of the content hash.
        return {
            "schema": _OBSERVATION_SCHEMA,
            "observation_id": observation_id,
            "facts": facts.to_dict(),
            "bound": bound.to_dict(),
            "activation_receipt_hash": activation_receipt_hash,
        }

    def put(
        self,
        *,
        observation_id: str,
        facts: ObservationFacts,
        bound: SurvivalBound,
        activation_receipt_hash: str,
    ) -> Path:
        """Derive ``in_bounds`` and persist the observation (atomic temp+rename)."""
        if not observation_id:
            raise ValueError("observation_id must be non-empty")
        if not activation_receipt_hash:
            raise ValueError("activation_receipt_hash must be non-empty")
        verdict = derive_in_bounds(facts, bound)
        identity = self._identity_dict(
            observation_id=observation_id,
            facts=facts,
            bound=bound,
            activation_receipt_hash=activation_receipt_hash,
        )
        payload = dict(identity)
        payload["in_bounds"] = verdict.in_bounds
        payload["reasons"] = list(verdict.reasons)
        payload["content_hash"] = content_hash(canonical_json(identity))

        trial_dir = self._dir / _trial_key(facts.trial_id)
        trial_dir.mkdir(parents=True, exist_ok=True)
        path = trial_dir / f"{observation_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def load_for_trial(self, trial_id: str) -> list[LiveSurvivalObservationReceipt]:
        """Load, integrity-check, and RE-DERIVE in_bounds for every observation of
        a trial. Returns plain ``LiveSurvivalObservationReceipt``s (sorted by
        observation_id) for the existing walk/assembler. Empty list on a clean miss.
        Raises :class:`ObservationReceiptTamperError` on any failed check."""
        trial_dir = self._dir / _trial_key(trial_id)
        if not trial_dir.exists():
            return []
        out: list[LiveSurvivalObservationReceipt] = []
        for path in sorted(trial_dir.glob("*.json")):
            d = json.loads(path.read_text())
            facts = ObservationFacts.from_dict(d["facts"])
            bound = SurvivalBound.from_dict(d["bound"])
            observation_id = d["observation_id"]
            activation_receipt_hash = d["activation_receipt_hash"]

            identity = self._identity_dict(
                observation_id=observation_id,
                facts=facts,
                bound=bound,
                activation_receipt_hash=activation_receipt_hash,
            )
            recomputed = content_hash(canonical_json(identity))
            if d.get("content_hash") != recomputed:
                raise ObservationReceiptTamperError(
                    f"observation {observation_id!r} (trial {trial_id!r}) failed "
                    f"content integrity: declared {d.get('content_hash')!r} != "
                    f"recomputed {recomputed!r}"
                )
            if facts.trial_id != trial_id:
                raise ObservationReceiptTamperError(
                    f"observation at key for {trial_id!r} carries trial_id "
                    f"{facts.trial_id!r} (swap / key collision)"
                )
            verdict = derive_in_bounds(facts, bound)
            if verdict.in_bounds != d.get("in_bounds"):
                raise ObservationReceiptTamperError(
                    f"observation {observation_id!r} (trial {trial_id!r}): stored "
                    f"in_bounds {d.get('in_bounds')!r} != re-derived "
                    f"{verdict.in_bounds!r} — producer-derived is not "
                    f"producer-trusted"
                )

            out.append(
                LiveSurvivalObservationReceipt(
                    trial_id=trial_id,
                    observation_id=observation_id,
                    observed_at=facts.observed_at,
                    in_bounds=verdict.in_bounds,
                    activation_receipt_hash=activation_receipt_hash,
                    disqualifying_events=facts.disqualifying_events,
                )
            )
        return out


class ReplayHoldoutReceiptTamperError(ValueError):
    """A persisted replay/holdout receipt failed its integrity check on load: the
    declared ``content_hash`` (over inputs) does not match the recompute, the stored
    ``trial_id`` does not match the requested key, OR the stored verdict does not match
    the value re-derived from the stored facts. The last is the load-bearing one:
    producer-derived is not producer-trusted — a refused run re-stamped passed is
    caught by re-derivation."""


_REPLAY_SCHEMA = "promotion_replay_holdout_v0"


class ReplayHoldoutReceiptStore:
    """File-per-trial store for replay/holdout receipts under
    ``<root>/promotion_evidence/replay_holdouts/<trial_key>.json`` (one per trial).

    ``put()`` derives the verdict (``derive_replay_verdict``) and persists the INPUT
    facts plus the derived verdict; ``content_hash`` covers INPUTS only. ``load_for_trial``
    recomputes the content hash (tampered facts), checks the stored ``trial_id`` (swap),
    and **re-derives the verdict from the stored facts, refusing a disagreement** — then
    emits a plain ``promotion_evidence.ReplayHoldoutReceipt`` (carrying the RE-DERIVED
    pass/fail) for the existing walk/assembler, which independently checks corpus-frozen
    match, harness walkability, and the pass bool. A legitimately-refused run still loads
    (as ``passed=False``); only integrity failures raise. The stored verdict is never
    trusted.
    """

    def __init__(self, root: Path | str):
        self._dir = Path(root) / _EVIDENCE_DIRNAME / _REPLAY_HOLDOUTS_DIRNAME

    @property
    def directory(self) -> Path:
        return self._dir

    def put(self, facts: ReplayHoldoutFacts) -> Path:
        """Derive the verdict and persist the replay/holdout receipt (atomic)."""
        verdict = derive_replay_verdict(facts)
        identity = dict(facts.to_dict())
        identity["schema"] = _REPLAY_SCHEMA
        payload = dict(identity)
        payload["verdict"] = verdict.verdict
        payload["reasons"] = list(verdict.reasons)
        payload["content_hash"] = content_hash(canonical_json(identity))

        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_trial_key(facts.trial_id)}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def load_for_trial(self, trial_id: str) -> ReplayHoldoutReceipt | None:
        """Load, integrity-check, and RE-DERIVE the verdict for a trial's replay/holdout
        receipt. Returns ``None`` on a clean miss (the walk treats a missing replay as
        refused-MISSING). Raises :class:`ReplayHoldoutReceiptTamperError` on any failed
        check."""
        path = self._dir / f"{_trial_key(trial_id)}.json"
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        facts = ReplayHoldoutFacts.from_dict(d)

        identity = dict(facts.to_dict())
        identity["schema"] = _REPLAY_SCHEMA
        recomputed = content_hash(canonical_json(identity))
        if d.get("content_hash") != recomputed:
            raise ReplayHoldoutReceiptTamperError(
                f"replay/holdout for trial {trial_id!r} failed content integrity: "
                f"declared {d.get('content_hash')!r} != recomputed {recomputed!r}"
            )
        if facts.trial_id != trial_id:
            raise ReplayHoldoutReceiptTamperError(
                f"replay/holdout at key for {trial_id!r} carries trial_id "
                f"{facts.trial_id!r} (swap / key collision)"
            )
        verdict = derive_replay_verdict(facts)
        if verdict.verdict != d.get("verdict"):
            raise ReplayHoldoutReceiptTamperError(
                f"replay/holdout for trial {trial_id!r}: stored verdict "
                f"{d.get('verdict')!r} != re-derived {verdict.verdict!r} — "
                f"producer-derived is not producer-trusted"
            )

        basis = (
            "non-regression vs comparator baseline on frozen corpus"
            if verdict.passed
            else "refused: " + ",".join(verdict.reasons)
        )
        return ReplayHoldoutReceipt(
            trial_id=facts.trial_id,
            replay_subject=facts.replay_subject,
            passed=verdict.passed,
            corpus_hash=facts.corpus_hash,
            frozen_corpus_hash=facts.frozen_corpus_hash,
            harness_version=facts.harness_version,
            comparator_baseline_id=facts.comparator_baseline_id,
            falsification_basis=basis,
        )


class OperatorBasisReceiptTamperError(ValueError):
    """A persisted operator-basis receipt failed its integrity check on load: the
    declared ``content_hash`` does not match the recompute, or the stored ``trial_id``
    does not match the requested key. Note: the operator's ``reviewed_verdict`` is an
    attested INPUT (in the hashed facts), so re-stamping it refused→basis_reviewed is a
    content tamper caught here — unlike observations/replay, whose verdicts are derived
    and excluded from the hash so re-derivation is the catch."""


_OPERATOR_BASIS_SCHEMA = "promotion_operator_basis_v0"


class OperatorBasisReceiptStore:
    """File-per-trial store for operator-basis receipts under
    ``<root>/promotion_evidence/operator_basis/<trial_key>.json`` (one per trial).

    Asymmetric with the other two stores ON PURPOSE: ``operator_basis_present`` is
    **consume-relative** — it cannot be derived from facts alone, only against the
    consumed bundle + promote clock. So ``put()`` persists facts (integrity only) and
    ``load_for_trial`` takes the consume-time inputs and runs
    ``derive_operator_basis_present``: it emits the existing simple
    ``promotion_evidence.OperatorBasisReceipt`` (which the assembler reads as
    ``operator_basis_present``) **only if the structural derivation passes** — bundle
    binding, before-the-transition, fresh, attested-reviewed. A structural failure
    returns ``None`` (the gate sees the basis absent → refused). The detached
    ``operator_basis_present=True`` has no path: you cannot get the receipt out without
    a matching consumed bundle and an in-time, fresh review. The deriver is the real
    gate; the assembler's bool is its shadow.
    """

    def __init__(self, root: Path | str):
        self._dir = Path(root) / _EVIDENCE_DIRNAME / "operator_basis"

    @property
    def directory(self) -> Path:
        return self._dir

    def put(self, facts: OperatorBasisFacts) -> Path:
        """Persist operator-basis facts (atomic). No verdict is derived here —
        ``operator_basis_present`` is consume-relative (see ``load_for_trial``)."""
        identity = dict(facts.to_dict())
        identity["schema"] = _OPERATOR_BASIS_SCHEMA
        payload = dict(identity)
        payload["content_hash"] = content_hash(canonical_json(identity))

        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_trial_key(facts.trial_id)}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def load_for_trial(
        self,
        trial_id: str,
        *,
        consumed_bundle_hash: str,
        promote_reading: MonotonicReading,
        freshness_horizon_ns: int,
    ) -> OperatorBasisReceipt | None:
        """Integrity-check, then DERIVE ``operator_basis_present`` against the consumed
        bundle + promote clock. Emits the simple ``OperatorBasisReceipt`` iff present;
        ``None`` on a clean miss OR a structural failure (the gate then refuses
        operator-basis-absent). Raises :class:`OperatorBasisReceiptTamperError` on an
        integrity failure (tampered facts / restamped verdict / trial swap)."""
        path = self._dir / f"{_trial_key(trial_id)}.json"
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        facts = OperatorBasisFacts.from_dict(d)

        identity = dict(facts.to_dict())
        identity["schema"] = _OPERATOR_BASIS_SCHEMA
        recomputed = content_hash(canonical_json(identity))
        if d.get("content_hash") != recomputed:
            raise OperatorBasisReceiptTamperError(
                f"operator-basis for trial {trial_id!r} failed content integrity: "
                f"declared {d.get('content_hash')!r} != recomputed {recomputed!r}"
            )
        if facts.trial_id != trial_id:
            raise OperatorBasisReceiptTamperError(
                f"operator-basis at key for {trial_id!r} carries trial_id "
                f"{facts.trial_id!r} (swap / key collision)"
            )

        verdict = derive_operator_basis_present(
            facts,
            consumed_bundle_hash=consumed_bundle_hash,
            promote_reading=promote_reading,
            freshness_horizon_ns=freshness_horizon_ns,
        )
        if not verdict.present:
            return None  # structural failure -> gate sees operator-basis absent

        return OperatorBasisReceipt(
            trial_id=facts.trial_id,
            operator_actor=facts.operator_id,
            promotion_basis=facts.promotion_basis,
            scope=facts.scope,
            explicitly_not_auto_baseline=True,
        )


__all__ = [
    "ActivationReceiptStore",
    "ActivationReceiptTamperError",
    "ObservationReceiptStore",
    "ObservationReceiptTamperError",
    "ReplayHoldoutReceiptStore",
    "ReplayHoldoutReceiptTamperError",
    "OperatorBasisReceiptStore",
    "OperatorBasisReceiptTamperError",
]
