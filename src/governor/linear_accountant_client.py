"""
Status: SPEC-honoring harness stub
Authority: test/demo contract witness only
Promotion: replace with real cross-repo client when wiring lands

Linear Accountant client seam — S2 (wicket→LA) and S3 (LA→effect).

This module is the AG-side seam against the Linear Accountant v0 reference
boundary at ``~/git/linearaccountant/src/lib.rs`` (frozen 2026-06-04). It is a
*harness stub*: no real transport, no HTTP/RPC layer, no shared client base.
Downstream LA callables are injected so call counts are testable.

Contract honored (verbatim shape from LA ``lib.rs``):

  CapacityRequest{request_id, actor, action, target, scope, requested_capacity,
                  eligibility_reference, eligibility_valid_until, expires_after,
                  idempotency_key}
  ConsumeRequest{consumption_event_id, token_id, actor, action, target, amount,
                 scope}

  CapacityDecision := Granted{token_id, granted_capacity, scope, expires_at,
                              receipt}
                   | Denied{denial_reason, receipt}

  ConsumptionDecision := Consumed | AlreadyConsumed | InsufficientCapacity
                       | Expired | Revoked | UnknownToken | ScopeMismatch

AG-side refusal semantics (closed vocabulary; do not extend here):

  standing_required, standing_expired, admission_denied,
  admission_gap_accounted, capacity_refused, already_consumed,
  dangling_receipt_reference

S2 invariants enforced PRE-call:

  * ``eligibility_reference`` (the cooked-context field that carries the
    admission receipt id, per ``working/linear-accountant-handoff.md`` §2) must
    be present. Absence → ``admission_denied`` refusal; LA request callable is
    not invoked.
  * Admission receipt id must be resolvable via the injected
    ``admission_verifier`` (a callable that returns True iff the receipt id
    exists). Lookup miss → ``dangling_receipt_reference`` refusal; LA request
    callable is not invoked.

S3 invariants enforced POST-call (mapped from LA's ConsumptionDecision):

  * ``Consumed`` → effect allowed; client returns ``Consumed`` verdict.
  * ``AlreadyConsumed`` → ``already_consumed`` refusal (replay kill).
  * ``InsufficientCapacity`` → ``capacity_refused`` refusal.
  * ``Expired``, ``Revoked``, ``UnknownToken``, ``ScopeMismatch`` — **SPEC
    does not define how AG should map these to the closed AG refusal-kind
    set.** Provisionally routed to ``capacity_refused`` (the closest LA-side
    consume-refused bucket) so that the client never crashes and the closed-set
    invariant holds, but the implementer is REQUIRED to flag HIGH escalation
    until the operator ratifies a per-variant mapping.

Forbidden in this module (per operator preflight):

  * No new ArtifactKind / UseKind.
  * No transport abstraction. Downstream LA endpoints are plain callables
    injected at construction.
  * No schema unification across tools.
  * No shared client base class. One module, one client.
  * No changing LA contract field names to make tests prettier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

# ---------------------------------------------------------------------------
# Closed AG-side refusal vocabulary.
#
# Do not extend in this module. The set is owned by S4-lite (see
# ``working/campaign-standing-before-spendability.md`` §S4-lite).
# ---------------------------------------------------------------------------

REFUSAL_STANDING_REQUIRED = "standing_required"
REFUSAL_STANDING_EXPIRED = "standing_expired"
REFUSAL_ADMISSION_DENIED = "admission_denied"
REFUSAL_ADMISSION_GAP_ACCOUNTED = "admission_gap_accounted"
REFUSAL_CAPACITY_REFUSED = "capacity_refused"
REFUSAL_ALREADY_CONSUMED = "already_consumed"
REFUSAL_DANGLING_RECEIPT_REFERENCE = "dangling_receipt_reference"
# Added 2026-06-09 by S4-lite ratification per codex adversarial nomenclature
# review: distinct LA ConsumptionDecision variants each map to their own kind
# so `why <receipt-id>` can distinguish capacity shortage from token expiry,
# revocation, unknown token, or scope mismatch. Collapsing them under
# capacity_refused would overclaim (LA Expired is token expiry, not standing
# expiry; UnknownToken is a dangling token, not a missing receipt; etc.).
REFUSAL_TOKEN_EXPIRED = "token_expired"
REFUSAL_TOKEN_REVOKED = "token_revoked"
REFUSAL_UNKNOWN_TOKEN = "unknown_token"
REFUSAL_SCOPE_MISMATCH = "scope_mismatch"

CLOSED_REFUSAL_KINDS = frozenset(
    {
        REFUSAL_STANDING_REQUIRED,
        REFUSAL_STANDING_EXPIRED,
        REFUSAL_ADMISSION_DENIED,
        REFUSAL_ADMISSION_GAP_ACCOUNTED,
        REFUSAL_CAPACITY_REFUSED,
        REFUSAL_ALREADY_CONSUMED,
        REFUSAL_DANGLING_RECEIPT_REFERENCE,
        REFUSAL_TOKEN_EXPIRED,
        REFUSAL_TOKEN_REVOKED,
        REFUSAL_UNKNOWN_TOKEN,
        REFUSAL_SCOPE_MISMATCH,
    }
)

# Bypass kind. NOT a refusal — it is an operator-ratified MVP-harness bypass of
# an AG-internal BA3 budget surface (per c0-resolved bypass contract). Emitted
# by the runtime supervisor / D0 harness at suppression time, NOT by this
# client. Listed here as vocabulary documentation only; do not construct a
# RefusalResult with this kind (the __post_init__ check will reject it).
BYPASS_BA3_FOR_MVP = "BA3_BYPASSED_FOR_MVP"


# The closed set this client may emit at this seam. Runtime invariant on
# `_emit_refusal_receipt`. Note this is the FULL S4-lite refusal set minus
# `standing_required` / `dangling_receipt_reference` (those are owned by
# standing/wicket seams and must not be re-minted here). LA-seam refusals
# include `admission_denied` because the gate that fires on a missing
# `admission_receipt_id` lives in this client.
_LA_SEAM_REFUSAL_KINDS = frozenset({
    REFUSAL_ADMISSION_DENIED,
    REFUSAL_ADMISSION_GAP_ACCOUNTED,
    REFUSAL_CAPACITY_REFUSED,
    REFUSAL_ALREADY_CONSUMED,
    REFUSAL_DANGLING_RECEIPT_REFERENCE,
    REFUSAL_TOKEN_EXPIRED,
    REFUSAL_TOKEN_REVOKED,
    REFUSAL_UNKNOWN_TOKEN,
    REFUSAL_SCOPE_MISMATCH,
})

# Gate name this seam emits under. Stable; do not rename without S4-lite reopen.
LA_SEAM_GATE = "la_seam"

# D0d-b: positive verdict used for granted-capacity and consumed-capacity
# receipts. Drawn from the GateReceipt closed verdict vocabulary
# (``VALID_VERDICTS`` in ``gate_receipt.py``: pass / warn / block /
# observe / proceed). "pass" is the verdict GateReceiptSystem already
# accepts; no new vocabulary is invented here. This deliberately mirrors
# D0c-a's WICKET_SEAM_ADMIT_VERDICT pattern. NOT a refusal kind —
# capacity granted / capacity consumed is positive chain completeness,
# NOT a widening of CLOSED_REFUSAL_KINDS.
LA_SEAM_POSITIVE_VERDICT = "pass"


class ReceiptSink(Protocol):
    """Thin sink contract — duck-typed against ``GateReceiptSystem.emit``.

    Same shape as the standing/wicket seam contract; redeclared here to
    keep the LA client surface self-contained (no cross-module client
    base class per the seam's anti-coupling rule).
    """

    def emit(
        self,
        gate: str,
        verdict: str,
        subject_kind: str,
        subject_bytes: bytes,
        evidence_bundle: dict[str, Any],
        gate_config: dict[str, Any],
        **kwargs: Any,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# LA decision tags. These mirror the variant names in
# ``~/git/linearaccountant/src/lib.rs``. They are NOT a new schema — they are
# the existing LA contract, transcribed for the seam to dispatch on.
# ---------------------------------------------------------------------------

# CapacityDecision variants
LA_DECISION_GRANTED = "Granted"
LA_DECISION_DENIED = "Denied"

# ConsumptionDecision variants
LA_DECISION_CONSUMED = "Consumed"
LA_DECISION_ALREADY_CONSUMED = "AlreadyConsumed"
LA_DECISION_INSUFFICIENT_CAPACITY = "InsufficientCapacity"
LA_DECISION_EXPIRED = "Expired"
LA_DECISION_REVOKED = "Revoked"
LA_DECISION_UNKNOWN_TOKEN = "UnknownToken"
LA_DECISION_SCOPE_MISMATCH = "ScopeMismatch"


# ---------------------------------------------------------------------------
# Cooked-context dataclasses.
#
# Field names mirror ``lib.rs`` verbatim where AG-side and LA-side semantics
# coincide. The AG-side cooked context carries one extra field,
# ``admission_receipt_id``, which is the AG-cooked admission receipt id. The
# client copies it into ``eligibility_reference`` when invoking LA, per the
# §2 handoff packet shape ("basis is a reference to AG's eligibility
# finding").
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CookedCapacityRequest:
    """AG-cooked request prior to LA invocation.

    ``admission_receipt_id`` is the AG-side cooked admission receipt id (the
    output of S1 wicket→standing seam). It populates the LA-side
    ``eligibility_reference`` field per the handoff §2 packet shape.
    """

    request_id: str
    actor: str
    action: str
    target: str
    scope: str
    requested_capacity: int
    admission_receipt_id: Optional[str]
    eligibility_valid_until: int
    expires_after: int
    idempotency_key: Optional[str] = None


@dataclass(frozen=True)
class CookedConsumeRequest:
    """AG-cooked consume payload. Mirrors LA's ConsumeRequest verbatim."""

    consumption_event_id: str
    token_id: Any  # opaque; LA owns the type
    actor: str
    action: str
    target: str
    amount: int
    scope: str


# ---------------------------------------------------------------------------
# Result types.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefusalResult:
    """An AG-side refusal. ``kind`` is drawn from the closed refusal set.

    D0a: ``receipt_id`` is the id of the GateReceipt minted at refusal
    time. None when the client was constructed without an injected
    ``receipt_sink`` (back-compat). ``parent_receipt_id`` carries the
    admission receipt id when the refusal cited admission as its basis;
    in the demo chain, the admission receipt is the wicket-seam receipt
    that authorized (or refused) admission, and that id is what the LA
    seam cites as parent so ``governor why`` walks LA → admission →
    standing.
    """

    kind: str
    detail: str
    la_decision: Optional[dict] = None  # raw LA response if the call happened
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in CLOSED_REFUSAL_KINDS:
            # Invariant: the refusal kind must come from the closed set. If
            # this fires, the client invented a kind, which violates the S2/S3
            # contract and must be a code bug.
            raise ValueError(
                f"refusal kind {self.kind!r} is not in the closed refusal set"
            )


@dataclass(frozen=True)
class GrantedResult:
    """LA returned ``Granted``; AG carries the token reference downstream.

    D0d-b: ``receipt_id`` is the id of the AG-side ``la_seam`` positive
    GateReceipt minted when the LA decision is ``Granted`` (verdict="pass").
    ``None`` when the client was constructed without an injected
    ``receipt_sink`` (back-compat); populated on the emission path so the
    orchestrator can carry it forward as ``parent_grant_receipt_id`` for
    the subsequent ``consume()`` call and ``governor why`` walks
    consume → granted → admission. ``parent_receipt_id`` is the
    admission_receipt_id cited as the basis for the capacity request, so
    the receipt links back to the wicket admission.
    """

    token_id: Any
    granted_capacity: int
    scope: str
    expires_at: int
    receipt: Any
    la_decision: dict
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None


@dataclass(frozen=True)
class ConsumedResult:
    """LA returned ``Consumed``; the effect is allowed downstream.

    D0d-b: ``receipt_id`` is the id of the AG-side ``la_seam`` positive
    GateReceipt minted when the LA decision is ``Consumed`` (verdict="pass").
    ``None`` when the client was constructed without an injected
    ``receipt_sink`` (back-compat). ``parent_receipt_id`` is the
    ``parent_grant_receipt_id`` passed by the caller (the orchestrator
    threads ``GrantedResult.receipt_id`` here), so ``governor why`` walks
    consume → granted through real ids.
    """

    token_id: Any
    consumed_amount: int
    remaining_capacity: int
    receipt: Any
    la_decision: dict
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None


# ---------------------------------------------------------------------------
# The client.
# ---------------------------------------------------------------------------


class LinearAccountantClient:
    """SPEC-honoring harness stub for the AG → LA seam.

    Downstream LA endpoints are injected as plain callables:

      * ``request_capacity_callable(la_request: dict, now: int) -> dict``
        Returns a dict with ``decision`` key set to one of
        ``LA_DECISION_GRANTED`` / ``LA_DECISION_DENIED`` plus the variant's
        fields per ``lib.rs``.
      * ``consume_callable(la_request: dict, now: int) -> dict``
        Returns a dict with ``decision`` key set to one of the seven
        ConsumptionDecision variants.
      * ``admission_verifier(admission_receipt_id: str) -> bool``
        True iff the AG-cooked admission receipt id is resolvable. A False
        return means the cited receipt is dangling.

    No real transport. No retries. No timeouts. No HTTP. No RPC. No queue.
    """

    def __init__(
        self,
        request_capacity_callable: Callable[[dict, int], dict],
        consume_callable: Callable[[dict, int], dict],
        admission_verifier: Callable[[str], bool],
        receipt_sink: Optional[ReceiptSink] = None,
    ) -> None:
        self._request_capacity_callable = request_capacity_callable
        self._consume_callable = consume_callable
        self._admission_verifier = admission_verifier
        self._receipt_sink = receipt_sink

    # ------------------------------------------------------------------
    # Refusal-time GateReceipt emission (D0a).
    # ------------------------------------------------------------------

    def _emit_refusal_receipt(
        self,
        *,
        refusal_kind: str,
        detail: str,
        subject_kind: str,
        subject_bytes: bytes,
        evidence_extra: dict[str, Any],
        parent_receipt_id: Optional[str],
    ) -> Optional[str]:
        """Emit an LA-seam refusal-time GateReceipt; return its id.

        Runtime invariant: ``refusal_kind`` MUST be in
        ``_LA_SEAM_REFUSAL_KINDS``. Returns None when no sink is wired
        (back-compat). ``parent_receipt_id`` is cited in
        ``parent_receipt_ids`` when set so ``governor why`` walks LA →
        admission → standing.
        """
        if refusal_kind not in _LA_SEAM_REFUSAL_KINDS:
            raise AssertionError(
                f"linear_accountant_client attempted to emit refusal kind "
                f"{refusal_kind!r}, which is not in the closed set "
                f"{sorted(_LA_SEAM_REFUSAL_KINDS)}"
            )
        if self._receipt_sink is None:
            return None
        evidence_bundle: dict[str, Any] = {
            "refusal_kind": refusal_kind,
            "detail": detail,
            "parent_receipt_ids": (
                [parent_receipt_id] if parent_receipt_id else []
            ),
        }
        evidence_bundle.update(evidence_extra)
        receipt = self._receipt_sink.emit(
            gate=LA_SEAM_GATE,
            verdict="block",
            subject_kind=subject_kind,
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S2_S3_la", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id

    # ------------------------------------------------------------------
    # D0d-b — happy-path GateReceipt emission (granted / consumed).
    # ------------------------------------------------------------------

    def _emit_grant_receipt(
        self,
        *,
        cooked_request: CookedCapacityRequest,
        la_response: dict,
        parent_receipt_id: Optional[str],
    ) -> Optional[str]:
        """Emit an LA-seam capacity-granted GateReceipt; return its id.

        D0d-b positive counterpart to ``_emit_refusal_receipt``. Verdict
        is "pass" — drawn from the closed positive-verdict vocabulary in
        GateReceiptSystem (``VALID_VERDICTS``); no new verdict name
        invented. Returns ``None`` when no sink is wired (back-compat).

        ``parent_receipt_id`` is the admission_receipt_id cited as the
        request's basis. It is recorded in
        ``evidence_bundle.parent_receipt_ids`` so ``governor why`` walks
        granted → admission. The closed-vocab ``refusal_kind`` field is
        deliberately omitted — this is a non-refusal receipt and
        ``why._classify`` correctly routes it to ``non_refusal`` / OK.

        Per D0d-b spec: NOT a refusal kind. We do NOT widen
        ``_LA_SEAM_REFUSAL_KINDS`` and do NOT introduce a typed positive
        enum — the descriptive marker ``la_outcome="granted"`` lives only
        as a key inside the open ``evidence_bundle`` dict.
        """
        if self._receipt_sink is None:
            return None
        s_bytes = (
            f"{cooked_request.request_id}|{cooked_request.actor}|"
            f"{cooked_request.action}|{cooked_request.target}|"
            f"{cooked_request.scope}|{cooked_request.requested_capacity}|"
            f"{cooked_request.admission_receipt_id or ''}|GRANTED"
        ).encode("utf-8")
        evidence_bundle: dict[str, Any] = {
            # Descriptive (NOT closed-vocab) marker.
            "la_outcome": "granted",
            "request_id": cooked_request.request_id,
            "actor": cooked_request.actor,
            "action": cooked_request.action,
            "target": cooked_request.target,
            "scope": cooked_request.scope,
            "requested_capacity": cooked_request.requested_capacity,
            "granted_capacity": la_response.get("granted_capacity"),
            "cited_admission_receipt_id": cooked_request.admission_receipt_id,
            # Token id is opaque to AG; repr keeps the bundle stable for
            # content-addressing regardless of LA's token type.
            "token_id_repr": repr(la_response.get("token_id")),
            "parent_receipt_ids": (
                [parent_receipt_id] if parent_receipt_id else []
            ),
        }
        receipt = self._receipt_sink.emit(
            gate=LA_SEAM_GATE,
            verdict=LA_SEAM_POSITIVE_VERDICT,
            subject_kind="la_capacity_request",
            subject_bytes=s_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S2_S3_la", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id

    def _emit_consume_receipt(
        self,
        *,
        cooked_request: CookedConsumeRequest,
        la_response: dict,
        parent_receipt_id: Optional[str],
    ) -> Optional[str]:
        """Emit an LA-seam capacity-consumed GateReceipt; return its id.

        D0d-b positive counterpart to ``_emit_refusal_receipt`` for the
        consume path. Verdict is "pass". Returns ``None`` when no sink
        is wired (back-compat).

        ``parent_receipt_id`` is the prior ``GrantedResult.receipt_id``
        threaded in by the caller (orchestrator / runner). It is recorded
        in ``evidence_bundle.parent_receipt_ids`` so ``governor why``
        walks consumed → granted → admission → standing → finding.

        Per D0d-b spec: NOT a refusal kind; descriptive marker
        ``la_outcome="consumed"`` only.
        """
        if self._receipt_sink is None:
            return None
        s_bytes = (
            f"{cooked_request.consumption_event_id}|"
            f"{cooked_request.token_id!r}|{cooked_request.actor}|"
            f"{cooked_request.action}|{cooked_request.target}|"
            f"{cooked_request.amount}|{cooked_request.scope}|CONSUMED"
        ).encode("utf-8")
        evidence_bundle: dict[str, Any] = {
            # Descriptive (NOT closed-vocab) marker.
            "la_outcome": "consumed",
            "consumption_event_id": cooked_request.consumption_event_id,
            "actor": cooked_request.actor,
            "action": cooked_request.action,
            "target": cooked_request.target,
            "amount": cooked_request.amount,
            "scope": cooked_request.scope,
            "token_id_repr": repr(cooked_request.token_id),
            "consumed_amount": la_response.get("consumed_amount"),
            "remaining_capacity": la_response.get("remaining_capacity"),
            "parent_receipt_ids": (
                [parent_receipt_id] if parent_receipt_id else []
            ),
        }
        receipt = self._receipt_sink.emit(
            gate=LA_SEAM_GATE,
            verdict=LA_SEAM_POSITIVE_VERDICT,
            subject_kind="la_consume_request",
            subject_bytes=s_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S2_S3_la", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id

    def _refuse(
        self,
        *,
        kind: str,
        detail: str,
        subject_kind: str,
        subject_bytes: bytes,
        evidence_extra: dict[str, Any],
        parent_receipt_id: Optional[str],
        la_decision: Optional[dict] = None,
    ) -> RefusalResult:
        """Build a RefusalResult with a freshly minted receipt id.

        Centralizes the "emit then construct" pattern so each refusal
        path stays one expression instead of a manual two-step that can
        forget to populate ``receipt_id``.
        """
        rid = self._emit_refusal_receipt(
            refusal_kind=kind,
            detail=detail,
            subject_kind=subject_kind,
            subject_bytes=subject_bytes,
            evidence_extra=evidence_extra,
            parent_receipt_id=parent_receipt_id,
        )
        return RefusalResult(
            kind=kind,
            detail=detail,
            la_decision=la_decision,
            receipt_id=rid,
            parent_receipt_id=parent_receipt_id,
        )

    # ------------------------------------------------------------------
    # S2 — wicket → LA seam.
    # ------------------------------------------------------------------

    def request_capacity(
        self,
        cooked_request: CookedCapacityRequest,
        now: int,
    ) -> GrantedResult | RefusalResult:
        """Refuse pre-call when the admission basis is missing/dangling.

        S2 invariant: no capacity request without an admission receipt.
        The injected ``request_capacity_callable`` is NEVER invoked when the
        request fails this gate.
        """
        admission_receipt_id = cooked_request.admission_receipt_id
        # The LA-seam subject is "what was requested" — the cooked
        # capacity request shape, encoded stably.
        s_kind = "la_capacity_request"
        s_bytes = (
            f"{cooked_request.request_id}|{cooked_request.actor}|"
            f"{cooked_request.action}|{cooked_request.target}|"
            f"{cooked_request.scope}|{cooked_request.requested_capacity}|"
            f"{admission_receipt_id or ''}"
        ).encode("utf-8")
        evidence_common: dict[str, Any] = {
            "request_id": cooked_request.request_id,
            "actor": cooked_request.actor,
            "action": cooked_request.action,
            "target": cooked_request.target,
            "scope": cooked_request.scope,
            "requested_capacity": cooked_request.requested_capacity,
            "cited_admission_receipt_id": admission_receipt_id,
        }

        # Gate 1: admission receipt id present?
        if admission_receipt_id is None or not admission_receipt_id.strip():
            return self._refuse(
                kind=REFUSAL_ADMISSION_DENIED,
                detail=(
                    "no admission_receipt_id in cooked context; "
                    "S2 invariant: no admission → no capacity request"
                ),
                subject_kind=s_kind,
                subject_bytes=s_bytes,
                evidence_extra=evidence_common,
                # No admission receipt → no parent to cite.
                parent_receipt_id=None,
            )

        # Gate 2: admission receipt id resolves?
        if not self._admission_verifier(admission_receipt_id):
            return self._refuse(
                kind=REFUSAL_DANGLING_RECEIPT_REFERENCE,
                detail=(
                    f"admission_receipt_id {admission_receipt_id!r} cited "
                    "in cooked context but not resolvable; this is the "
                    "confabulated-receipt path"
                ),
                subject_kind=s_kind,
                subject_bytes=s_bytes,
                evidence_extra=evidence_common,
                # The cited id dangles — we record it in evidence but do
                # NOT cite it as parent (citing an unverifiable id would
                # paint a chain to a receipt that does not exist).
                parent_receipt_id=None,
            )

        # Gate passed. Build the LA-shaped request (field names verbatim
        # from lib.rs) and dispatch.
        la_request = {
            "request_id": cooked_request.request_id,
            "actor": cooked_request.actor,
            "action": cooked_request.action,
            "target": cooked_request.target,
            "scope": cooked_request.scope,
            "requested_capacity": cooked_request.requested_capacity,
            # The AG admission_receipt_id is the basis carried into LA's
            # eligibility_reference per handoff §2: "basis is a reference to
            # AG's eligibility finding ... never the capacity itself."
            "eligibility_reference": admission_receipt_id,
            "eligibility_valid_until": cooked_request.eligibility_valid_until,
            "expires_after": cooked_request.expires_after,
            "idempotency_key": cooked_request.idempotency_key,
        }

        la_response = self._request_capacity_callable(la_request, now)
        decision = la_response.get("decision")

        if decision == LA_DECISION_GRANTED:
            # D0d-b: mint the positive (granted) GateReceipt and propagate
            # its id onto GrantedResult so the orchestrator / runner can
            # thread it as parent on the subsequent consume receipt.
            # ``cited_admission_receipt_id`` was verified above, so it is
            # safe to cite as the parent on this receipt.
            grant_rid = self._emit_grant_receipt(
                cooked_request=cooked_request,
                la_response=la_response,
                parent_receipt_id=admission_receipt_id,
            )
            return GrantedResult(
                token_id=la_response["token_id"],
                granted_capacity=la_response["granted_capacity"],
                scope=la_response["scope"],
                expires_at=la_response["expires_at"],
                receipt=la_response["receipt"],
                la_decision=la_response,
                receipt_id=grant_rid,
                parent_receipt_id=admission_receipt_id,
            )

        if decision == LA_DECISION_DENIED:
            # LA returns Denied with a free-text reason for stale-eligibility /
            # zero-capacity / insufficient-stock at request time. Per the
            # campaign §S2 stage-distinctness rule and the closed AG refusal
            # vocabulary, all such request-time denials surface to AG as
            # ``capacity_refused``. This is the only request-time denial kind
            # in the closed AG set that maps to "LA said no at request time".
            return self._refuse(
                kind=REFUSAL_CAPACITY_REFUSED,
                detail=str(la_response.get("denial_reason", "")),
                subject_kind=s_kind,
                subject_bytes=s_bytes,
                evidence_extra={**evidence_common, "la_response": la_response},
                parent_receipt_id=admission_receipt_id,
                la_decision=la_response,
            )

        # Unknown CapacityDecision variant. Don't crash — surface as a
        # refusal so the closed-set invariant holds.
        return self._refuse(
            kind=REFUSAL_CAPACITY_REFUSED,
            detail=f"unrecognized LA CapacityDecision variant: {decision!r}",
            subject_kind=s_kind,
            subject_bytes=s_bytes,
            evidence_extra={**evidence_common, "la_response": la_response},
            parent_receipt_id=admission_receipt_id,
            la_decision=la_response,
        )

    # ------------------------------------------------------------------
    # S3 — LA → effect seam.
    # ------------------------------------------------------------------

    def consume(
        self,
        cooked_request: CookedConsumeRequest,
        now: int,
        *,
        parent_grant_receipt_id: Optional[str] = None,
    ) -> ConsumedResult | RefusalResult:
        """Invoke LA consume; map result into Consumed or closed-set refusal.

        S3 invariant: the effect requires a ``Consumed`` verdict. Replay of
        the same ``consumption_event_id`` → ``already_consumed`` refusal.
        Insufficient capacity at consume → ``capacity_refused``.

        LA ConsumptionDecision mappings (ratified at S4-lite 2026-06-09 per
        codex adversarial nomenclature review):

        * ``Expired``       → ``token_expired`` (LA-side token expiry; distinct
          from standing-side ``standing_expired``)
        * ``Revoked``       → ``token_revoked``
        * ``UnknownToken``  → ``unknown_token`` (LA does not recognize this
          ``token_id``; distinct from ``dangling_receipt_reference`` which is
          an AG-side admission_receipt_id miss before LA is consulted)
        * ``ScopeMismatch`` → ``scope_mismatch``

        D0d-b: ``parent_grant_receipt_id`` is the prior
        ``GrantedResult.receipt_id`` threaded in by the caller
        (orchestrator / runner). It is cited as the parent on the
        consumed-capacity GateReceipt (verdict="pass") so ``governor
        why`` walks consumed → granted. Optional for back-compat — when
        callers don't thread it, the consume receipt has no parent and
        is a chain origin from AG's gate-receipt vantage.
        """
        la_request = {
            "consumption_event_id": cooked_request.consumption_event_id,
            "token_id": cooked_request.token_id,
            "actor": cooked_request.actor,
            "action": cooked_request.action,
            "target": cooked_request.target,
            "amount": cooked_request.amount,
            "scope": cooked_request.scope,
        }

        # Stable subject encoding for the consume seam.
        s_kind = "la_consume_request"
        s_bytes = (
            f"{cooked_request.consumption_event_id}|"
            f"{cooked_request.token_id!r}|{cooked_request.actor}|"
            f"{cooked_request.action}|{cooked_request.target}|"
            f"{cooked_request.amount}|{cooked_request.scope}"
        ).encode("utf-8")
        evidence_common: dict[str, Any] = {
            "consumption_event_id": cooked_request.consumption_event_id,
            "actor": cooked_request.actor,
            "action": cooked_request.action,
            "target": cooked_request.target,
            "amount": cooked_request.amount,
            "scope": cooked_request.scope,
        }

        la_response = self._consume_callable(la_request, now)
        decision = la_response.get("decision")

        if decision == LA_DECISION_CONSUMED:
            # D0d-b: mint the positive (consumed) GateReceipt citing the
            # prior grant receipt as parent.
            consume_rid = self._emit_consume_receipt(
                cooked_request=cooked_request,
                la_response=la_response,
                parent_receipt_id=parent_grant_receipt_id,
            )
            return ConsumedResult(
                token_id=la_response["token_id"],
                consumed_amount=la_response["consumed_amount"],
                remaining_capacity=la_response["remaining_capacity"],
                receipt=la_response["receipt"],
                la_decision=la_response,
                receipt_id=consume_rid,
                parent_receipt_id=parent_grant_receipt_id,
            )

        if decision == LA_DECISION_ALREADY_CONSUMED:
            # S3 replay kill. The downstream effect counter must not advance.
            return self._refuse(
                kind=REFUSAL_ALREADY_CONSUMED,
                detail=(
                    "LA returned AlreadyConsumed; consume event id was "
                    "previously spent against this token"
                ),
                subject_kind=s_kind,
                subject_bytes=s_bytes,
                evidence_extra={**evidence_common, "la_response": la_response},
                # consume() does not carry an admission_receipt_id (LA
                # owns the token at this point). Parent linkage at consume
                # time is not available without breaking the existing
                # CookedConsumeRequest shape, which is forbidden ("do not
                # add new vocabulary"). Parent linkage stays None.
                parent_receipt_id=None,
                la_decision=la_response,
            )

        if decision == LA_DECISION_INSUFFICIENT_CAPACITY:
            return self._refuse(
                kind=REFUSAL_CAPACITY_REFUSED,
                detail=(
                    f"LA returned InsufficientCapacity; remaining="
                    f"{la_response.get('remaining_capacity')!r}, "
                    f"requested={la_response.get('requested_amount')!r}"
                ),
                subject_kind=s_kind,
                subject_bytes=s_bytes,
                evidence_extra={**evidence_common, "la_response": la_response},
                parent_receipt_id=None,
                la_decision=la_response,
            )

        # Ratified per-variant mapping (S4-lite 2026-06-09; codex review):
        # each LA failure variant gets its own AG refusal kind, because each
        # is a SPEC-visible failure shape with its own receipt fields.
        # Collapsing under capacity_refused would lose the distinction S5
        # `why <receipt-id>` needs to explain *which* token state failed.
        _LA_TO_REFUSAL = {
            LA_DECISION_EXPIRED: REFUSAL_TOKEN_EXPIRED,
            LA_DECISION_REVOKED: REFUSAL_TOKEN_REVOKED,
            LA_DECISION_UNKNOWN_TOKEN: REFUSAL_UNKNOWN_TOKEN,
            LA_DECISION_SCOPE_MISMATCH: REFUSAL_SCOPE_MISMATCH,
        }
        if decision in _LA_TO_REFUSAL:
            return self._refuse(
                kind=_LA_TO_REFUSAL[decision],
                detail=f"LA returned {decision}",
                subject_kind=s_kind,
                subject_bytes=s_bytes,
                evidence_extra={**evidence_common, "la_response": la_response},
                parent_receipt_id=None,
                la_decision=la_response,
            )

        # Unknown ConsumptionDecision variant. Don't crash — surface as a
        # capacity refusal so the closed-set invariant holds.
        return self._refuse(
            kind=REFUSAL_CAPACITY_REFUSED,
            detail=(
                f"unrecognized LA ConsumptionDecision variant: {decision!r}"
            ),
            subject_kind=s_kind,
            subject_bytes=s_bytes,
            evidence_extra={**evidence_common, "la_response": la_response},
            parent_receipt_id=None,
            la_decision=la_response,
        )
