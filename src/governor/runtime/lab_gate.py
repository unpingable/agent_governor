# SPDX-License-Identifier: Apache-2.0
"""Bootstrap-lab LA-backed effect gate.

The first real organ of the AG dogfood loop. It sits at the supervisor's
existing tool-effect boundary (`_handle_tool_proposed`) and makes one inner
tool class (WRITE) cross **only** after the Linear Accountant authorizes
consumption against a session-scoped capacity grant.

Atlas spine (``~/git/playground/AGENT-GOV-ATLAS.md``):

    standing → admission → spendability (LA) → execution (AG) → receipt

LA decides spendability; AG decides whether/how the admitted effect crosses;
the AG receipt *witnesses* the LA decision and the effect — it manufactures
neither authority.

Hard scope: ``profile = bootstrap_lab``. This path may consume governed
capacity and emit real (lab-scoped) gate receipts, but its evidence **cannot**
mint production-promotion evidence and **cannot** mutate ``ControlBaseline``.
That is enforced by :func:`forbid_promotion`, not left to honor.

Slice-1 boundary (``working/campaign-ag-walking-skeleton.md``):
- the LA seam is the **injected, contract-faithful** ``LinearAccountantClient``
  (the same seam LA's own tests + the orchestrator use). No real cross-repo
  transport here — that bridge is a separate, flagged follow-on.
- NO ``ActiveTunableStore`` involvement (max_actions is capacity authority,
  owned by LA — not an AG self-annealing tunable). P4 stays parked.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from governor.linear_accountant_client import (
    ConsumedResult,
    CookedCapacityRequest,
    CookedConsumeRequest,
    GrantedResult,
    LinearAccountantClient,
    RefusalResult,
)

BOOTSTRAP_LAB_PROFILE = "bootstrap_lab"


class LabScopeViolation(Exception):
    """Raised when bootstrap-lab evidence is asked to do something its scope
    forbids (mint promotion evidence, mutate a production baseline)."""


def forbid_promotion(profile: str | None) -> None:
    """The enforced fence. Any promotion / baseline-mutation path that might
    ingest lab-produced evidence must call this first. Bootstrap-lab evidence
    is barred — by exception, not by convention.

    Acceptance §8/§9: no promotion evidence; no production-baseline mutation;
    cannot satisfy the parked P4 trial.
    """
    if profile == BOOTSTRAP_LAB_PROFILE:
        raise LabScopeViolation(
            "bootstrap_lab evidence cannot mint production-promotion evidence "
            "or mutate ControlBaseline (campaign-ag-walking-skeleton fence)"
        )


@dataclass
class LabEffectDecision:
    """Outcome of the LA-backed effect gate for one tool proposal."""

    allowed: bool
    reason: str
    # LA decision identity, for the AG event/receipt chain (acceptance §7).
    la_kind: Optional[str] = None          # refusal kind, or "consumed"
    token_id: Any = None
    consume_receipt_id: Optional[str] = None
    remaining_capacity: Optional[int] = None


@dataclass
class LabGate:
    """Session-scoped LA-backed effect gate.

    One capacity grant per supervised inner session (the bounded allocation);
    each governed WRITE proposal performs a distinct ``consume(amount=1)``
    against that grant, keyed by the proposal identity so a replayed proposal
    is refused (``already_consumed``) rather than double-spent.
    """

    la_client: LinearAccountantClient
    session_id: str
    actor: str
    scope: str
    action: str = "tool_effect"
    # Set by :meth:`acquire_grant`.
    token_id: Any = None
    grant_receipt_id: Optional[str] = None
    grant_refusal: Optional[str] = None
    profile: str = BOOTSTRAP_LAB_PROFILE
    # Serialization point: AG's own lock around the consume call so concurrent
    # proposals cannot race the gate. LA's accountant is itself single-writer;
    # this lock makes AG's decision-then-act atomic from the gate's side too.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # Logical clock (LA's Tick is caller-supplied; there is no ambient now()).
    # Starts at the grant tick and advances one per consume, staying within the
    # token's freshness horizon. NOT wall/monotonic time — a monotonic_ms value
    # would read as "expired" against a logically-bounded grant.
    _tick: int = field(default=0, repr=False)

    def acquire_grant(
        self,
        *,
        requested_capacity: int,
        admission_receipt_id: str | None,
        eligibility_valid_until: int,
        expires_after: int,
        now: int,
    ) -> GrantedResult | RefusalResult:
        """Obtain the one session-scoped capacity grant.

        Spine discipline: capacity requires admission. The grant cites an
        admission receipt id; LA refuses (``admission_denied`` /
        ``dangling_receipt_reference``) when it is absent/unresolvable — AG
        does not manufacture the admission.
        """
        self._tick = now  # logical clock starts at the grant tick
        req = CookedCapacityRequest(
            request_id=f"labgrant_{self.session_id}",
            actor=self.actor,
            action=self.action,
            target=self.scope,
            scope=self.scope,
            requested_capacity=requested_capacity,
            admission_receipt_id=admission_receipt_id,
            eligibility_valid_until=eligibility_valid_until,
            expires_after=expires_after,
            idempotency_key=f"labgrant_{self.session_id}",
        )
        result = self.la_client.request_capacity(req, now)
        if isinstance(result, GrantedResult):
            self.token_id = result.token_id
            self.grant_receipt_id = result.receipt_id
        else:
            self.grant_refusal = result.kind
        return result

    def decide_write_effect(
        self,
        *,
        tool_call_id: str,
        now: int | None = None,
    ) -> LabEffectDecision:
        """Decide whether one WRITE proposal may cross, via LA ``consume``.

        ``consumption_event_id`` is derived from the proposal identity so a
        replayed proposal maps to ``already_consumed`` (replay-kill), and a
        fresh proposal against an exhausted grant maps to ``capacity_refused``
        — in both cases AG refuses **before** the effect.
        """
        if self.token_id is None:
            # No grant ⇒ fail closed. The session never obtained capacity.
            return LabEffectDecision(
                allowed=False,
                reason=f"no_session_grant ({self.grant_refusal or 'not acquired'})",
                la_kind=self.grant_refusal or "no_session_grant",
            )

        if now is None:
            self._tick += 1
            now = self._tick
        cooked = CookedConsumeRequest(
            consumption_event_id=f"{self.session_id}:{tool_call_id}",
            token_id=self.token_id,
            actor=self.actor,
            action=self.action,
            target=self.scope,
            amount=1,
            scope=self.scope,
        )
        with self._lock:
            result = self.la_client.consume(
                cooked, now, parent_grant_receipt_id=self.grant_receipt_id
            )

        if isinstance(result, ConsumedResult):
            return LabEffectDecision(
                allowed=True,
                reason="la_consumed",
                la_kind="consumed",
                token_id=result.token_id,
                consume_receipt_id=result.receipt_id,
                remaining_capacity=result.remaining_capacity,
            )
        # RefusalResult — closed kind set (capacity_refused / already_consumed /
        # scope_mismatch / token_expired / …). The effect does not cross.
        return LabEffectDecision(
            allowed=False,
            reason=result.detail,
            la_kind=result.kind,
            consume_receipt_id=result.receipt_id,
        )
