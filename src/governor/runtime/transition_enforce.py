# SPDX-License-Identifier: Apache-2.0
"""Stage 3b: the live accounting consequence (3b1) and the first real bounded effect (3b2).

Orders the real chain so the durable record is replay-legible at every crash point:

    AuthorizedTransition -> receiver correspondence -> durable LA consume (the burn)
      -> durable EffectAttemptReceipt -> create_new(marker) -> durable terminal outcome receipt

LA is the **sole authoritative burn**; the receiver only checks correspondence. The actuator is one
deliberately boring idempotent effect — exclusive `create_new` of a fixed-content marker beneath a
sandbox root (effect class `create_marker_v1`): no arbitrary shell, no overwrite, no general write.

Terminal vocabulary (a returned write success is NOT testimony — `EffectSucceeded` requires post-effect
verification that the path exists and its content hash matches):

    NotConsumed + Refused
    Consumed + EffectSucceeded
    Consumed + EffectFailed
    Consumed + OutcomeUnknown   (and Conflict for wrong content — never success)

Claim (after 3b2): **at-most-once authority consumption and replay-legible execution of one idempotent
bounded effect through the live AG supervisor.** Not generic exactly-once effects; not a general actuator
framework.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

# Terminal states.
T_REFUSED = "not_consumed_refused"
T_SUCCEEDED = "consumed_effect_succeeded"
T_FAILED = "consumed_effect_failed"
T_NOT_ATTEMPTED = "consumed_effect_not_attempted"
T_UNKNOWN = "consumed_outcome_unknown"
T_CONFLICT = "consumed_effect_conflict"

# Crash points (force process death for replay-legibility tests).
CRASH_BEFORE_CONSUME = "before_consume"
CRASH_AFTER_CONSUME = "after_consume"
CRASH_AFTER_ATTEMPT = "after_attempt"
CRASH_AFTER_EFFECT = "after_effect"
CRASH_AFTER_SUCCESS = "after_success"


def _append(durable_path: Path, record: dict[str, Any]) -> None:
    with open(durable_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def composed_snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Recompute the canonical hash of a composed execution snapshot (Stage 3c).

    Must reproduce the kernel's `ComposedExecutionSnapshot::snapshot_hash` byte-for-byte: RFC 8785 (JCS)
    canonicalization -> SHA-256, prefixed `sha256:`. For the snapshot's shape (all-ASCII keys; string,
    bool and integer values) this is exactly `json.dumps(sort_keys, separators=(",",":"))`. The agreement
    is pinned by a cross-language regression test; do not let the two canonicalizations drift.
    """
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_snapshot_coherence(
    cev: str, snapshot: dict[str, Any], claimed_hash: str
) -> str | None:
    """Stage 3c coherence: does this snapshot pin the admission state that governed `cev`?

    Mirrors the kernel's `ComposedExecutionSnapshot::verify_consume_binding`. Returns an incoherence
    reason, or None when the snapshot coheres. A lossy snapshot (claims liveness but pins no execution
    clock) is rejected before the hash is trusted — that is the case the Lean
    `lossy_receipt_cannot_pin_snapshot` model rules out.
    """
    if snapshot.get("revalidation_live") and not snapshot.get("revalidated_at"):
        return "missing_revalidation_clock"
    if composed_snapshot_hash(snapshot) != claimed_hash:
        return "snapshot_hash_mismatch"
    if snapshot.get("consumption_event_id") != cev:
        return "consumption_event_mismatch"
    return None


def _refused(reason: str, *, durable_path: Path | None = None) -> dict[str, Any]:
    # Fail-closed is not fail-silent: record infrastructure refusal durably when a sink is available.
    if durable_path is not None:
        try:
            _append(Path(durable_path), {"kind": "infra_refusal", "reason": reason})
        except OSError:
            pass
    return {"result": T_REFUSED, "operational": False, "reason": reason}


class FakeActuator:
    """3b1 actuator: attempts no effect."""

    attempts_effect = False
    effect_class = "none"

    def describe(self) -> dict[str, Any]:
        return {"effect_class": self.effect_class}


class MarkerActuator:
    """3b2 effect: exclusive create-new of a fixed-content marker beneath `sandbox_root`."""

    attempts_effect = True
    effect_class = "create_marker_v1"

    def __init__(self, sandbox_root: Path, name: str, content: bytes):
        self.sandbox_root = Path(sandbox_root)
        # Canonical path beneath the sandbox root; no traversal.
        self.marker_path = self.sandbox_root / f"{name}.marker"
        self.content = content
        self.content_sha256 = hashlib.sha256(content).hexdigest()

    def describe(self) -> dict[str, Any]:
        return {
            "effect_class": self.effect_class,
            "marker_path": str(self.marker_path),
            "content_sha256": self.content_sha256,
        }

    def perform(self) -> str:
        """create_new only. Returns a terminal token after post-effect verification."""
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.marker_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # create-new only: an existing marker is not a fresh success.
            return T_CONFLICT
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(self.content)
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            return T_FAILED
        # Post-effect verification: a returned success is not enough.
        return T_SUCCEEDED if self._verify() else T_FAILED

    def _verify(self) -> bool:
        try:
            data = self.marker_path.read_bytes()
        except FileNotFoundError:
            return False
        return hashlib.sha256(data).hexdigest() == self.content_sha256


def enforce_chain(
    transition: Any,  # TransitionSubprocess
    la: Any,  # LASubprocess
    *,
    token_handle: str,
    scope: str,
    target: str,
    effect_class: str,
    operation_hash: str,
    consumer: str,
    eligibility_reference: str,
    capability_id: str,
    valid_until: int,
    now: int,
    durable_path: Path,
    actuator: Any = None,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """Run the enforce chain. Fail-closed (and durable-on-refusal) at every external boundary."""
    durable_path = Path(durable_path)
    if actuator is None:
        actuator = FakeActuator()

    # 1. LA mints the single-use capability.
    cap = la.issue_capability(token_handle, target, effect_class, capability_id, now=now)
    if cap is None:
        return _refused("la_unavailable_or_capability_refused", durable_path=durable_path)

    # 2. Build the chain bundle (LA-issued capability, verbatim).
    bundle_inner = {
        "office_outputs": {
            "standing": "verified", "standing_receipt_ref": eligibility_reference,
            "la_admission": "admitted", "la_consume": "consumed", "scope": scope, "target": target,
        },
        "capability": {
            "capability_id": cap["capability_id"], "scope": cap["scope"], "target": cap["target"],
            "effect_class": cap["effect_class"], "eligibility_reference": cap["eligibility_reference"],
            "expires_at": cap["expires_at"], "single_use": cap["single_use"],
        },
        "revalidation": {
            "standing_ref": eligibility_reference, "live": True, "valid_until": valid_until, "now": now,
        },
        "operation": {"operation_hash": operation_hash, "consumer": consumer},
        "requested": {
            "operation_hash": operation_hash, "consumer": consumer, "scope": scope, "target": target,
            "effect_class": effect_class, "capability_nonce": cap["capability_id"], "now": now,
        },
    }

    # 3. Receiver correspondence (no burn). Fail-closed -> refuse, never observe.
    corr = transition.correspondence_check(bundle_inner)
    if corr is None:
        return _refused("transition_unavailable", durable_path=durable_path)
    if corr.get("result") != "correspondence_ok":
        return _refused(f"correspondence_refused:{corr.get('stage')}:{corr.get('reason')}",
                        durable_path=durable_path)
    if corr.get("eligibility_reference") != eligibility_reference:
        return _refused("eligibility_reference_drift", durable_path=durable_path)
    cev = corr["consumption_event_id"]

    # Stage 3c: the kernel pins the composed admission snapshot that governs this effect. Require it
    # (fail-closed: a kernel that cannot pin the snapshot cannot be allowed to spend) and verify it
    # coheres before the burn, so the durable receipt provably describes the state that governed admission.
    snapshot = corr.get("composed_snapshot")
    snapshot_hash = corr.get("snapshot_hash")
    if snapshot is None or snapshot_hash is None:
        return _refused("composed_snapshot_missing", durable_path=durable_path)
    incoherence = verify_snapshot_coherence(cev, snapshot, snapshot_hash)
    if incoherence is not None:
        return _refused(f"composed_snapshot_incoherent:{incoherence}", durable_path=durable_path)

    # Crash point 1: before consume -> nothing spent; a new operation may be admitted later.
    if crash_at == CRASH_BEFORE_CONSUME:
        return {"result": "crashed_before_consume", "operational": False, "consumption_event_id": cev}

    # Durable composed snapshot — written BEFORE the consume so a crash after consume still reconstructs
    # with the governing admission snapshot attached (Stage 3c). LA has not yet burned anything here.
    _append(durable_path, {"kind": "composed_snapshot", "consumption_event_id": cev,
                           "snapshot_hash": snapshot_hash, "snapshot": snapshot})

    # 4. LA consume — the AUTHORITATIVE burn.
    dec = la.consume(
        {
            "consumption_event_id": cev, "token_id": token_handle, "actor": consumer,
            "action": "write", "target": target, "amount": 1, "scope": scope,
        },
        now,
    )
    if dec is None:
        return _refused("la_consume_unavailable", durable_path=durable_path)
    if dec.get("decision") != "Consumed":
        return _refused(f"consume_refused:{dec.get('decision')}", durable_path=durable_path)

    # 5. Durable ConsumeReceipt — after this, capacity is spent. References the composed snapshot hash so
    #    the burn is bound to the exact admission state that governed it (Stage 3c).
    _append(durable_path, {"kind": "consume_receipt", "consumption_event_id": cev,
                           "token_id": token_handle, "la_decision": dec, "operational": True,
                           "snapshot_hash": snapshot_hash})

    # Crash point 2: after consume, before attempt receipt -> Consumed + OutcomeUnknown.
    if crash_at == CRASH_AFTER_CONSUME:
        return {"result": "crashed", "at": CRASH_AFTER_CONSUME, "operational": True,
                "consumption_event_id": cev}

    if not actuator.attempts_effect:
        # 3b1 fake path: no effect attempted.
        _append(durable_path, {"kind": "effect_outcome", "consumption_event_id": cev,
                               "outcome": T_NOT_ATTEMPTED})
        return {"result": T_NOT_ATTEMPTED, "operational": True, "consumption_event_id": cev,
                "consume_receipt": dec}

    # 6. Durable EffectAttemptReceipt BEFORE the effect (carries marker path + content hash for reconcile).
    _append(durable_path, {"kind": "effect_attempt", "consumption_event_id": cev, **actuator.describe()})

    # Crash point 3: after attempt, before effect -> Consumed + OutcomeUnknown (marker absent).
    if crash_at == CRASH_AFTER_ATTEMPT:
        return {"result": "crashed", "at": CRASH_AFTER_ATTEMPT, "operational": True,
                "consumption_event_id": cev}

    # 7. The bounded effect.
    outcome = actuator.perform()

    # Crash point 4: after effect, before success receipt -> reconcile from marker state.
    if crash_at == CRASH_AFTER_EFFECT:
        return {"result": "crashed", "at": CRASH_AFTER_EFFECT, "operational": True,
                "consumption_event_id": cev}

    # 8. Durable terminal outcome receipt.
    _append(durable_path, {"kind": "effect_outcome", "consumption_event_id": cev, "outcome": outcome})

    if crash_at == CRASH_AFTER_SUCCESS:
        return {"result": "crashed", "at": CRASH_AFTER_SUCCESS, "operational": True,
                "consumption_event_id": cev}

    return {"result": outcome, "operational": True, "consumption_event_id": cev,
            "consume_receipt": dec}


def _reconcile_marker(attempt: dict[str, Any]) -> str:
    """Classify a crashed-after-attempt result from marker state. Never repeats the effect or mints
    authority — it only reads and classifies."""
    path = Path(attempt["marker_path"])
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        # Absent: indistinguishable between not-yet-attempted and failed-to-create -> a classed
        # non-effect terminal, never success.
        return T_UNKNOWN
    actual = hashlib.sha256(data).hexdigest()
    if actual == attempt["content_sha256"]:
        return T_SUCCEEDED  # recovered: the exact expected marker exists.
    return T_CONFLICT  # wrong content/type -> conflict, never success.


def reconstruct(durable_path: Path) -> dict[str, str]:
    """Replay the durable store into a terminal state per consumption_event_id. A spent event is always
    spent; reconstruction classifies the past, it never yields permission to replay."""
    durable_path = Path(durable_path)
    if not durable_path.exists():
        return {}
    records = [json.loads(l) for l in durable_path.read_text().splitlines() if l.strip()]
    consumes = {r["consumption_event_id"] for r in records if r["kind"] == "consume_receipt"}
    attempts = {r["consumption_event_id"]: r for r in records if r["kind"] == "effect_attempt"}
    outcomes = {r["consumption_event_id"]: r["outcome"] for r in records if r["kind"] == "effect_outcome"}

    terminal: dict[str, str] = {}
    for cev in consumes:
        if cev in outcomes:
            terminal[cev] = outcomes[cev]
        elif cev in attempts:
            terminal[cev] = _reconcile_marker(attempts[cev])
        else:
            terminal[cev] = T_UNKNOWN  # crash after consume, before attempt.
    return terminal


def reconstruct_composed(durable_path: Path) -> dict[str, dict[str, Any]]:
    """Stage 3c reconstruction: per consumption event, the terminal outcome **and** the governing composed
    admission snapshot, with coherence checked.

    Where `reconstruct` answers "was capacity spent, and how did the effect end?", this answers the
    stronger composed-coherence question: "under exactly which admission snapshot was this effect
    allowed, and does the durable chain prove it?" Each entry carries `outcome`, the `snapshot` and its
    `snapshot_hash`, `coherent` (bool), and `incoherence` (reason or None). Reconstruction classifies the
    past; it never repeats an effect or mints authority.

    Coherence fails when: no composed snapshot exists for a consumed event (`missing_snapshot`); the
    consume receipt references a different snapshot hash than the snapshot record (`consume_snapshot_hash_
    mismatch`); or the snapshot itself does not cohere (recomputed hash, consumption-event, or
    execution-clock — see `verify_snapshot_coherence`).
    """
    durable_path = Path(durable_path)
    if not durable_path.exists():
        return {}
    records = [json.loads(line) for line in durable_path.read_text().splitlines() if line.strip()]
    consumes = {r["consumption_event_id"]: r for r in records if r["kind"] == "consume_receipt"}
    snapshots = {r["consumption_event_id"]: r for r in records if r["kind"] == "composed_snapshot"}
    attempts = {r["consumption_event_id"]: r for r in records if r["kind"] == "effect_attempt"}
    outcomes = {r["consumption_event_id"]: r["outcome"] for r in records if r["kind"] == "effect_outcome"}

    out: dict[str, dict[str, Any]] = {}
    for cev, consume in consumes.items():
        if cev in outcomes:
            terminal = outcomes[cev]
        elif cev in attempts:
            terminal = _reconcile_marker(attempts[cev])
        else:
            terminal = T_UNKNOWN

        snap_rec = snapshots.get(cev)
        if snap_rec is None:
            coherent, incoherence, snapshot, snap_hash = False, "missing_snapshot", None, None
        else:
            snapshot = snap_rec.get("snapshot")
            snap_hash = snap_rec.get("snapshot_hash")
            reason = verify_snapshot_coherence(cev, snapshot, snap_hash)
            if reason is None and consume.get("snapshot_hash") != snap_hash:
                reason = "consume_snapshot_hash_mismatch"
            coherent, incoherence = (reason is None), reason

        out[cev] = {
            "outcome": terminal,
            "snapshot": snapshot,
            "snapshot_hash": snap_hash,
            "coherent": coherent,
            "incoherence": incoherence,
        }
    return out
