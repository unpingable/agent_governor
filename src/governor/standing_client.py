# SPDX-License-Identifier: Apache-2.0
"""
Status: SPEC-honoring harness stub
Authority: test/demo contract witness only
Promotion: replace with real cross-repo client when wiring lands

S1 seam: thin client surface for obtaining or verifying a standing receipt id
against the standing service (~/git/standing, Rust). No real transport. The
downstream standing lookup is an injectable callable, so tests can drive it
and the demo harness can wire a real subprocess/socket later without
touching this surface.

Surface kept thin:
    - ``StandingReceiptRef`` — caller-facing handle for a content-addressed
      standing receipt. Mirrors standing's own receipt shape: a content-hash
      ``digest`` (hex SHA-256) plus the receipt ``kind``. Field names match
      ``standing-receipt/src/receipt.rs`` verbatim.
    - ``StandingClient.verify(standing_receipt_id)`` — calls the injected
      downstream verifier to confirm a receipt exists. Returns the
      ``StandingReceiptRef`` on hit, raises ``DanglingStandingReceiptError``
      on miss. No silent ``None`` — refusal must be loud at this seam.

Refusal vocabulary is restricted to the closed S4-lite set (see
``working/campaign-standing-before-spendability.md``). This module emits
only ``standing_required`` and ``dangling_receipt_reference`` — the two
shapes the S1 invariant produces at this seam. Other kinds belong to other
seams (admission / capacity / consumption / expiry / bypass).

Separate from ``governor.standing`` (the validator-role substrate). This
client is the *consumer-of-remote-standing* seam, intentionally orthogonal
to the validator-role package per
``~/git/wicket/WICKET_REMOTE_STANDING_ADAPTER_GAP.md`` ("do not collapse
Standing AssertionGrant / StandingDecision with Wicket ActorStanding /
StandingClass"). No shared base class, no imports from ``governor.standing``
beyond what is exported at the package root.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol


# Closed refusal-kind vocabulary, restricted to what this seam emits.
# Full set lives in S4-lite; this module emits only its own kinds.
REFUSAL_KIND_STANDING_REQUIRED = "standing_required"
REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE = "dangling_receipt_reference"


# The closed set this client may emit at this seam. Runtime invariant:
# `_emit_refusal_receipt` rejects any kind outside this set. The wider
# S4-lite vocabulary lives in `linear_accountant_client.CLOSED_REFUSAL_KINDS`;
# this module deliberately constrains emission to the kinds it owns so
# that an accidental cross-seam invention surfaces here rather than
# laundering downstream.
_STANDING_SEAM_REFUSAL_KINDS = frozenset({
    REFUSAL_KIND_STANDING_REQUIRED,
    REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE,
})


class ReceiptSink(Protocol):
    """Thin sink contract — same shape as ``GateReceiptSystem.emit``.

    Injection-shaped per D0a constraint: no global singleton, no shared
    receipt-state import. Tests wire a real ``GateReceiptSystem`` writing
    to a tmp dir; the demo harness wires its real system instance.
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


# Gate name this seam emits under. Stable; do not rename without S4-lite reopen.
STANDING_SEAM_GATE = "standing_seam"

# D0d-b: positive verdict used for verified-standing receipts. Drawn from
# the GateReceipt closed verdict vocabulary (``VALID_VERDICTS`` in
# ``gate_receipt.py``: pass / warn / block / observe / proceed). "pass"
# is the verdict GateReceiptSystem already accepts; no new vocabulary is
# invented here. This deliberately mirrors D0c-a's WICKET_SEAM_ADMIT_VERDICT
# pattern. NOT a refusal kind — admission/verification is positive chain
# completeness, NOT a widening of CLOSED_REFUSAL_KINDS.
STANDING_SEAM_VERIFIED_VERDICT = "pass"


@dataclass(frozen=True)
class StandingReceiptRef:
    """Content-addressed standing receipt handle.

    Mirrors ``standing-receipt`` crate: ``digest`` is hex SHA-256 over
    canonical JSON of the receipt body (per standing's own canonical hash
    construction). ``kind`` is the standing-side receipt kind string
    (e.g. ``grant_issued``, ``grant_activated``, ``grant_used``).

    AG does not interpret these values; it carries them through as
    opaque references that the standing service is authoritative over.
    """

    digest: str
    kind: str


class StandingClientError(Exception):
    """Base error for the standing-client seam."""

    refusal_kind: str = ""
    # D0a: every refusal-time exception carries the emitted GateReceipt's
    # id once the receipt has been minted (None on construction; populated
    # by the client before raise). The id is what `governor why` walks.
    receipt_id: Optional[str] = None


class StandingRequiredError(StandingClientError):
    """Raised when no ``standing_receipt_id`` was supplied to a surface
    that requires one.

    Refusal kind: ``standing_required``. Closed-vocabulary; do not
    expand at this seam.
    """

    refusal_kind = REFUSAL_KIND_STANDING_REQUIRED

    def __init__(
        self,
        message: str = "standing_receipt_id required but not supplied",
        receipt_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.receipt_id = receipt_id


class DanglingStandingReceiptError(StandingClientError):
    """Raised when a ``standing_receipt_id`` was supplied but the
    injected downstream verifier reports no such receipt exists.

    The live re-enactment of the manufactured-receipts incident: the
    model can claim anything, but it cannot cite what was never minted.
    Refusal kind: ``dangling_receipt_reference``.
    """

    refusal_kind = REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE

    def __init__(
        self,
        standing_receipt_id: str,
        receipt_id: Optional[str] = None,
    ):
        self.standing_receipt_id = standing_receipt_id
        super().__init__(
            f"dangling standing receipt reference: {standing_receipt_id!r} not found by downstream verifier"
        )
        self.receipt_id = receipt_id


# Type alias for the injected downstream. The callable receives a
# standing receipt id (hex digest string) and returns the matching
# ``StandingReceiptRef`` if it exists, or ``None`` if it does not.
# No transport assumed; the harness can wire fakes/mocks/subprocess.
StandingVerifier = Callable[[str], Optional[StandingReceiptRef]]


class StandingClient:
    """Thin SPEC-honoring stub for obtaining/verifying standing receipts.

    The injected ``verify_fn`` is the only path to standing-service state.
    No HTTP/RPC/transport here — the harness or demo wires the real
    downstream when it lands.

    D0a: optionally accepts an injected ``receipt_sink`` (duck-typed against
    ``GateReceiptSystem``). When present, every refusal path emits a
    ``GateReceipt`` to the sink *before* the exception is raised, and the
    minted ``receipt_id`` is attached to the exception so callers (and the
    ``governor why`` chain walker) can resolve the refusal back to its
    receipt. Absent sink → exceptions still raise (back-compat), but no
    receipt is minted; ``receipt_id`` stays None.
    """

    def __init__(
        self,
        verify_fn: StandingVerifier,
        receipt_sink: Optional[ReceiptSink] = None,
    ):
        if verify_fn is None:
            raise ValueError("StandingClient requires an injected verify_fn")
        self._verify_fn = verify_fn
        self._receipt_sink = receipt_sink
        # D0d-b: side-channel for the most recently emitted verified-standing
        # receipt id. ``verify()`` returns ``StandingReceiptRef`` (a frozen
        # value type) for backward compatibility; the caller (WicketClient)
        # reads this attribute after a successful verify to use the minted
        # receipt id as parent linkage on its own admission receipt.
        # ``None`` until the first happy-path emission. NOT thread-safe; the
        # seam contract is one-call-at-a-time, same as the rest of the stub.
        self._last_verified_receipt_id: Optional[str] = None

    def _emit_refusal_receipt(
        self,
        *,
        refusal_kind: str,
        detail: str,
        standing_receipt_id: Optional[str],
    ) -> Optional[str]:
        """Emit a refusal-time GateReceipt; return its receipt_id.

        Runtime invariant: refusal_kind MUST be in
        ``_STANDING_SEAM_REFUSAL_KINDS``. This is the closed-vocab assertion
        per D0a — the seam refuses to mint a receipt with a kind it does
        not own.

        Returns None when no sink is wired (back-compat). Otherwise returns
        the receipt id minted by the sink.
        """
        if refusal_kind not in _STANDING_SEAM_REFUSAL_KINDS:
            # Closed-vocab guard. A bug in the seam, not a runtime data error.
            raise AssertionError(
                f"standing_client attempted to emit refusal kind "
                f"{refusal_kind!r}, which is not in the closed set "
                f"{sorted(_STANDING_SEAM_REFUSAL_KINDS)}"
            )
        if self._receipt_sink is None:
            return None
        evidence_bundle: dict[str, Any] = {
            "refusal_kind": refusal_kind,
            "detail": detail,
            # Standing seam is the chain origin — no parent_receipt_ids.
            # `why` terminates here cleanly.
            "parent_receipt_ids": [],
        }
        if standing_receipt_id is not None:
            evidence_bundle["cited_standing_receipt_id"] = standing_receipt_id
        # Subject bytes encode "what was checked" so identical refusals on
        # identical inputs content-address to the same receipt id.
        subject_bytes = (standing_receipt_id or "").encode("utf-8")
        receipt = self._receipt_sink.emit(
            gate=STANDING_SEAM_GATE,
            verdict="block",
            subject_kind="standing_receipt_id",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S1_standing", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id

    def _emit_verified_receipt(
        self,
        *,
        standing_receipt_id: str,
        ref: StandingReceiptRef,
        finding_id: Optional[str],
    ) -> Optional[str]:
        """Emit a standing-seam verified-standing GateReceipt; return its id.

        D0d-b: positive (admission) counterpart to ``_emit_refusal_receipt``.
        Verdict is "pass" — drawn from the closed positive-verdict
        vocabulary in GateReceiptSystem (``VALID_VERDICTS`` in
        ``gate_receipt.py``); no new verdict name invented. Returns
        ``None`` when no sink is wired (back-compat).

        ``finding_id`` is the NQ-side chain origin (when the chain is
        driven by an NQ finding). When provided, it is cited as the sole
        parent in ``evidence_bundle.parent_receipt_ids`` so ``governor
        why`` walks standing-verification → NQ finding. When ``None``
        (the chain is CLI-originated or stub-driven), the parent list
        stays empty and this receipt is the chain origin from AG's
        gate-receipt vantage.

        The closed-vocab ``refusal_kind`` field is deliberately omitted —
        this is a non-refusal receipt; ``why._classify`` correctly routes
        it to ``non_refusal`` / OK.

        Per D0d-b spec: this is NOT a refusal kind. We do NOT widen
        ``_STANDING_SEAM_REFUSAL_KINDS`` and do NOT introduce a typed
        positive-verdict enum — the descriptive marker
        ``verified_standing`` lives only as a key inside the open
        ``evidence_bundle`` dict.
        """
        if self._receipt_sink is None:
            return None
        evidence_bundle: dict[str, Any] = {
            # Descriptive (NOT closed-vocab) marker so callers /
            # ``governor why`` evidence renderers can recognize this as
            # an admission-side receipt. Internal-only; never promoted to
            # ``CLOSED_REFUSAL_KINDS``.
            "verified_standing": True,
            "cited_standing_receipt_id": standing_receipt_id,
            "standing_ref_kind": ref.kind,
            "standing_ref_digest": ref.digest,
            "parent_receipt_ids": (
                [finding_id] if finding_id else []
            ),
        }
        # Subject bytes encode "what was verified" so identical verifications
        # on identical inputs content-address to the same receipt id.
        subject_bytes = standing_receipt_id.encode("utf-8")
        receipt = self._receipt_sink.emit(
            gate=STANDING_SEAM_GATE,
            verdict=STANDING_SEAM_VERIFIED_VERDICT,
            subject_kind="standing_receipt_id",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S1_standing", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id

    def verify(
        self,
        standing_receipt_id: Optional[str],
        *,
        finding_id: Optional[str] = None,
    ) -> StandingReceiptRef:
        """Verify a ``standing_receipt_id`` exists at the downstream.

        - Missing/None/empty id → ``StandingRequiredError``
          (refusal_kind=``standing_required``).
        - Id present but downstream returns ``None`` →
          ``DanglingStandingReceiptError``
          (refusal_kind=``dangling_receipt_reference``).
        - Id present and downstream returns a ref → return the ref.

        When a ``receipt_sink`` is wired, both refusal paths emit a
        ``GateReceipt`` first and attach its ``receipt_id`` to the raised
        exception.

        D0d-b: when a ``receipt_sink`` is wired AND the verification
        succeeds, a verified-standing ``GateReceipt`` is also emitted
        (verdict="pass", gate="standing_seam"). The minted ``receipt_id``
        is stashed on ``self._last_verified_receipt_id`` so the caller
        (WicketClient) can read it without changing this method's return
        type. ``finding_id`` is plumbed into the emitted receipt's
        ``parent_receipt_ids`` so the chain walk surfaces
        standing-verification → NQ finding when an NQ-originated chain
        is in flight.
        """
        if standing_receipt_id is None or standing_receipt_id == "":
            rid = self._emit_refusal_receipt(
                refusal_kind=REFUSAL_KIND_STANDING_REQUIRED,
                detail="standing_receipt_id missing or empty in cooked context",
                standing_receipt_id=None,
            )
            raise StandingRequiredError(receipt_id=rid)
        ref = self._verify_fn(standing_receipt_id)
        if ref is None:
            rid = self._emit_refusal_receipt(
                refusal_kind=REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE,
                detail=(
                    f"standing receipt id {standing_receipt_id!r} cited but "
                    "downstream verifier returned no such receipt"
                ),
                standing_receipt_id=standing_receipt_id,
            )
            raise DanglingStandingReceiptError(
                standing_receipt_id, receipt_id=rid
            )
        # D0d-b: standing verified — emit the positive chain-completeness
        # receipt and stash its id on the side-channel attribute.
        self._last_verified_receipt_id = self._emit_verified_receipt(
            standing_receipt_id=standing_receipt_id,
            ref=ref,
            finding_id=finding_id,
        )
        return ref
