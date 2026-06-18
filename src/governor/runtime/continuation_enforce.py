# SPDX-License-Identifier: Apache-2.0
"""GAP-2 C3: the durable continuation burn — the agent must show a receipt to keep being an agent.

A continuation grant authorizes **one next-step attempt, not one successful effect**. So the burn is
durable, happens when the next step *enters* the governed path (before the per-effect transition gate),
and stays spent even if that downstream gate later refuses. The agent used its next breath to ask for
something; whether the something was admissible is a separate question. That is not free oxygen.

The single-use property lives in a **ledger**, not in memory (the LA lesson: if the burn matters, it
needs a ledger — otherwise "single-use" means "single-use unless the process gets bonked"). The records:

    continuation_presented   the BURN — grant_id + binds + presented_at. After this, the grant is spent.
    continuation_outcome     admitted_to_transition — the next step reached the transition gate.
    continuation_refusal     a non-burning refusal (no grant / decision refuse|escalate / fail-closed),
                             recorded so fail-closed is never fail-silent.

Replay (`reconstruct_continuation`) classifies each grant_id:

    unused                       no presented record
    spent_outcome_unknown        presented, no outcome  (crash after burn — NOT retryable; spent is spent)
    admitted_to_transition       presented + outcome    (the next step reached the transition gate)

A reused grant is refused by the durable presence of its first `continuation_presented` record — there is
no second burn.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Terminal reconstruction states (per grant_id).
C_UNUSED = "continuation_unused"
C_SPENT_UNKNOWN = "continuation_spent_outcome_unknown"
C_ADMITTED = "continuation_admitted_to_transition"

# The next-step outcome recorded once the burned step reaches the transition gate.
OUTCOME_ADMITTED = "admitted_to_transition"


def _append(ledger_path: Path, record: dict[str, Any]) -> None:
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def correspondence_refusal(grant: dict[str, Any], presentation: dict[str, Any], now: int) -> str | None:
    """Why a presented next step does not match its grant (no burn — the right grant stays unused). A
    transfer (different actor/session), a different chain tip/scope/class, or an expired grant all fail
    here. Mirrors the kernel `ContinuationConsumer::check_correspondence`."""
    if presentation.get("session_id") != grant.get("session_id"):
        return "session_mismatch"
    if presentation.get("actor_id") != grant.get("actor_id"):
        return "actor_mismatch"
    if presentation.get("chain_tip") != grant.get("chain_tip"):
        return "chain_tip_mismatch"
    if presentation.get("scope") != grant.get("scope"):
        return "scope_mismatch"
    if presentation.get("next_step_class") != grant.get("next_step_class"):
        return "next_step_class_mismatch"
    if now > grant.get("expires_at", 0):
        return "expired"
    return None


def _presented_ids(ledger_path: Path) -> set[str]:
    if not ledger_path.exists():
        return set()
    ids = set()
    for line in ledger_path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("kind") == "continuation_presented":
            ids.add(r["grant_id"])
    return ids


def present_continuation(
    ledger_path: Path, grant: dict[str, Any], presentation: dict[str, Any], now: int
) -> dict[str, Any]:
    """Present a next step against its grant and, on exact correspondence of an unexpired, **not-yet-
    presented** grant, durably BURN it. Returns {"result": "admitted"|"refused", "refusal": reason|None,
    "grant_id": ...}. The burn record is written and fsynced before this returns admitted, so the spend
    survives a crash before the transition gate runs."""
    ledger_path = Path(ledger_path)
    gid = grant.get("grant_id")

    refusal = correspondence_refusal(grant, presentation, now)
    if refusal is not None:
        # No burn: the grant for the right step remains unused (non-transferable).
        return {"result": "refused", "refusal": refusal, "grant_id": gid}

    # Single-use authority is the ledger's, not memory's: a grant already presented is spent.
    if gid in _presented_ids(ledger_path):
        return {"result": "refused", "refusal": "already_consumed", "grant_id": gid}

    # THE BURN. After this fsync, the grant is spent regardless of what the transition gate decides next.
    _append(ledger_path, {
        "kind": "continuation_presented", "grant_id": gid,
        "session_id": grant.get("session_id"), "actor_id": grant.get("actor_id"),
        "prior_chain_tip": grant.get("chain_tip"), "next_step_class": grant.get("next_step_class"),
        "scope": grant.get("scope"), "presented_at": now,
    })
    return {"result": "admitted", "refusal": None, "grant_id": gid}


def finalize_continuation(ledger_path: Path, grant_id: str) -> None:
    """Record that the burned next step reached the transition gate. Written AFTER the burn; a crash in
    between leaves the grant `spent_outcome_unknown` (spent, not retryable)."""
    _append(Path(ledger_path), {
        "kind": "continuation_outcome", "grant_id": grant_id, "outcome": OUTCOME_ADMITTED})


def record_continuation_refusal(ledger_path: Path, *, grant_id: str | None, reason: str) -> None:
    """Durably record a non-burning refusal (no grant issued, decision refuse/escalate, or fail-closed
    kernel) so fail-closed is never fail-silent. Best-effort: swallow OS errors."""
    try:
        _append(Path(ledger_path), {
            "kind": "continuation_refusal", "grant_id": grant_id, "reason": reason})
    except OSError:
        pass


def reconstruct_continuation(ledger_path: Path) -> dict[str, str]:
    """Replay the durable ledger into a terminal state per grant_id. A spent grant is always spent;
    reconstruction classifies the past, it never yields permission to re-present."""
    ledger_path = Path(ledger_path)
    if not ledger_path.exists():
        return {}
    records = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
    presented = {r["grant_id"] for r in records if r.get("kind") == "continuation_presented"}
    outcomes = {r["grant_id"] for r in records if r.get("kind") == "continuation_outcome"}
    terminal: dict[str, str] = {}
    for gid in presented:
        terminal[gid] = C_ADMITTED if gid in outcomes else C_SPENT_UNKNOWN
    return terminal
