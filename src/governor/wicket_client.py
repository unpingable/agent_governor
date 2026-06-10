# SPDX-License-Identifier: Apache-2.0
"""
Status: SPEC-honoring harness stub
Authority: test/demo contract witness only
Promotion: replace with real cross-repo client when wiring lands

S1 seam: thin client surface for calling wicket's admissibility preflight
with a fully cooked context. Caller cooks; wicket accounts. This client
performs the AG-side pre-call refusal: when the cooked context lacks a
verifiable standing receipt id, refuse before the wicket-check callable
ever runs, so the downstream call-count stays at zero (the S1 invariant).

Surface kept thin:
    - ``CookedContext`` — dataclass mirroring the wicket SPEC §4 named
      fields that the S1 seam needs (actor_standing, scope_assertion,
      precedence, revocation, claimed_basis, plus the verbs the call
      acts on — actor / intended_action / operation_class / target /
      expected_effect / call_timestamp). Plus the AG-side bridging field
      ``standing_receipt_id`` per
      ``~/git/wicket/WICKET_REMOTE_STANDING_ADAPTER_GAP.md`` (the
      remote-standing seam wicket itself does not yet absorb).
    - ``WicketClient.check(cooked_context)`` — verifies standing receipt
      first; on AG-side refusal returns a ``WicketRefusal`` *without*
      invoking the injected wicket-check callable. On success, passes
      ``cooked_context`` through verbatim to the callable and returns
      its result.

Refusal vocabulary is restricted to the closed S4-lite set. This module
emits only ``standing_required`` and ``dangling_receipt_reference`` — the
two shapes the S1 invariant produces at this seam. Admission verdicts
(authorized / advisory_only / denied / gap / unaccounted) come from the
downstream wicket-check callable and are returned as ``WicketVerdict``.

Per the cook-translation-authority maxim
(``~/git/wlp/WLP_RECEIVER_GATE_CANDIDATE.md``, cited from the wicket gap
spec): the cook may translate testimony into policy vocabulary; it may
not let testimony choose the vocabulary. The cooked-context fields here
use wicket-owned names; ``standing_receipt_id`` is an AG-named handle for
the remote-standing seam, deliberately not an aliased import of
standing's wire names.

Separate from ``governor.wicket`` if/when that lands; this client is the
S1 plumbing seam, not the kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from governor.standing_client import (
    REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE,
    REFUSAL_KIND_STANDING_REQUIRED,
    DanglingStandingReceiptError,
    ReceiptSink,
    StandingClient,
    StandingRequiredError,
)


# Closed refusal-kind vocabulary, restricted to what this seam emits.
# Full set lives in S4-lite; admission/capacity/consumption kinds live
# at later seams.
REFUSAL_KIND_STANDING_REQUIRED_LOCAL = REFUSAL_KIND_STANDING_REQUIRED
REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE_LOCAL = REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE

# Closed-vocab set this seam may emit. Runtime invariant on
# `_emit_refusal_receipt`. The wicket seam emits only the two
# standing-shaped refusals it produces pre-call; downstream admission
# verdicts (authorized/denied/gap/etc.) come from the wicket-check
# callable and are NOT minted by this client.
_WICKET_SEAM_REFUSAL_KINDS = frozenset({
    REFUSAL_KIND_STANDING_REQUIRED,
    REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE,
})

# Gate name this seam emits under.
WICKET_SEAM_GATE = "wicket_seam"

# D0c-a: positive verdict used for authorized-admission receipts. Drawn
# from the GateReceipt closed verdict vocabulary (VALID_VERDICTS in
# ``gate_receipt.py``: pass / warn / block / observe / proceed). "pass"
# is the verdict GateReceiptSystem already accepts for admit-style
# decisions; no new vocabulary is invented here.
WICKET_SEAM_ADMIT_VERDICT = "pass"


@dataclass(frozen=True)
class ActorStanding:
    """Mirrors wicket SPEC §4 ``actor_standing`` field.

    ``cls`` corresponds to SPEC ``class`` — renamed to avoid Python keyword
    collision. ``provenance`` is one of ``caller_asserted``, ``attested``,
    ``verified`` per SPEC §4.2 (v1: only ``caller_asserted`` is mapped;
    others are model-unaccounted).
    """

    cls: str
    provenance: str


@dataclass(frozen=True)
class ScopeAssertion:
    """Mirrors wicket SPEC §4.6 ``scope_assertion`` field. Caller-cooked."""

    scope_includes_target: bool
    provenance: str
    evidence_refs: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class Precedence:
    """Mirrors wicket SPEC §4.7 ``precedence`` field. Caller-cooked.

    ``resolution`` ∈ {``active``, ``superseded``, ``ambiguous``, ``unresolved``}.
    ``superseded_by`` is optional rule ref when superseded.
    """

    resolution: str
    provenance: str
    evidence_refs: tuple = field(default_factory=tuple)
    superseded_by: Optional[str] = None


@dataclass(frozen=True)
class Revocation:
    """Mirrors wicket SPEC §4.8 ``revocation`` field. Caller-cooked.

    Two booleans plus provenance + evidence refs. Required so the caller
    cannot omit the question.
    """

    basis_revoked: bool
    standing_forbidden: bool
    provenance: str
    evidence_refs: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class CookedContext:
    """The fully-cooked Intent shape the wicket kernel consumes.

    Field names match wicket SPEC §4 verbatim, with two exceptions:

    1. ``actor_standing.class`` becomes ``actor_standing.cls`` (Python
       keyword collision).
    2. ``standing_receipt_id`` is an AG-side bridging field per
       ``WICKET_REMOTE_STANDING_ADAPTER_GAP.md``. Wicket SPEC v0.3 does
       not yet absorb it; the AG client refuses-on-its-absence before
       the wicket callable runs. When/if wicket absorbs it (per the gap
       note's "anticipated, not specified" plan), this field becomes
       part of the cooked context wicket itself reads.

    ``claimed_basis`` is left as a free-form mapping in this stub —
    populated per wicket SPEC §4 ``claimed_basis`` shape (rule +
    evidence_refs), but not exhaustively typed here. Real consumer
    wiring will type it; the S1 seam does not need to.
    """

    actor: str
    actor_standing: ActorStanding
    intended_action: str
    operation_class: str
    target: str
    claimed_basis: Mapping[str, Any]
    precedence: Precedence
    revocation: Revocation
    expected_effect: str
    call_timestamp: str
    standing_receipt_id: Optional[str] = None
    scope_assertion: Optional[ScopeAssertion] = None
    prev_receipt_hash: Optional[str] = None


@dataclass(frozen=True)
class WicketRefusal:
    """AG-side pre-call refusal. The wicket-check callable was NOT invoked.

    ``refusal_kind`` is restricted to the closed S4-lite vocabulary; this
    seam emits only ``standing_required`` or ``dangling_receipt_reference``.
    Detail field carries the offending id (if any) for receipt logging.

    D0a: ``receipt_id`` is the id of the GateReceipt minted at refusal
    time. None when the client was constructed without an injected
    ``receipt_sink`` (back-compat); populated on the emission paths so
    callers can pass it to ``governor why``. ``parent_receipt_id`` carries
    the standing-side refusal receipt id when the wicket refusal was
    *caused by* a standing-side refusal (the standing client minted its
    own receipt first); the wicket emission then cites that id as its
    parent so the chain walk surfaces standing → wicket.
    """

    refusal_kind: str
    detail: str
    standing_receipt_id: Optional[str] = None
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None


@dataclass(frozen=True)
class WicketVerdict:
    """Pass-through container for whatever the downstream wicket-check
    callable returns.

    The S1 seam does not interpret the verdict; it just routes it. The
    downstream is responsible for the wicket SPEC §7/§8 verdict shape
    (surface_verdict, dimensions, reason_codes, allowed, forbidden,
    receipt). AG stores the result by content-address downstream.

    D0c-a: ``receipt_id`` is the id of the wicket-seam authorized-admission
    GateReceipt minted when the standing receipt verifies and the wicket
    callable runs. None when the client was constructed without an
    injected ``receipt_sink`` (back-compat) — emission is sink-gated, same
    as refusal emission. ``parent_receipt_id`` carries the verified
    standing receipt id when the standing client minted one (sink-wired
    standing path); it is cited as the parent on the admission receipt so
    ``governor why`` walks wicket-admission → standing through real ids,
    not a synthesized link.

    Why two optional fields rather than a richer admission result type:
    the call sites (D0c orchestrator, tests) only need ``receipt_id`` to
    carry forward as ``admission_receipt_id`` for LA. The existing
    ``value`` field is the verdict pass-through that the SPEC §7/§8
    consumer already reads.
    """

    value: Any
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None


# Type alias for the injected downstream wicket-check callable. Receives
# the cooked context; returns whatever the wicket kernel produces. No
# transport assumed; the harness can wire a fake, a subprocess, or a
# real wicket library binding.
WicketCheckFn = Callable[[CookedContext], Any]


class WicketClient:
    """Thin SPEC-honoring stub for invoking wicket admissibility preflight.

    Pre-call refusal happens at the AG-side before the wicket callable
    runs. This is the seam where the S1 invariant is mechanical: missing
    or dangling ``standing_receipt_id`` → zero downstream calls.

    D0a: optionally accepts an injected ``receipt_sink`` (duck-typed
    against ``GateReceiptSystem``). When present, every wicket-side
    refusal path emits a ``GateReceipt`` and populates
    ``WicketRefusal.receipt_id``. When the refusal was caused by a
    standing-side refusal, the emitted wicket receipt's evidence bundle
    cites the standing receipt id under ``parent_receipt_ids`` so the
    chain walker surfaces the standing → wicket linkage. Absent sink →
    refusals still return WicketRefusal with ``receipt_id=None`` for
    back-compat.

    D0c-a: the symmetric authorized-admission emission. When the standing
    receipt verifies and the wicket-check callable returns a verdict, the
    client emits a ``GateReceipt`` with verdict="pass" (gate
    "wicket_seam") and cites the verified standing receipt id as parent.
    The emitted receipt id is propagated onto ``WicketVerdict.receipt_id``
    so downstream LA can use it as ``admission_receipt_id`` and
    ``governor why`` walks wicket-admission → standing through real ids.
    Closes the "one synthesized link" debt surfaced by D0a. Same sink
    gating: absent sink → no admission emission, ``receipt_id=None``.
    """

    def __init__(
        self,
        standing_client: StandingClient,
        wicket_check_fn: WicketCheckFn,
        receipt_sink: Optional[ReceiptSink] = None,
    ):
        if standing_client is None:
            raise ValueError("WicketClient requires a StandingClient")
        if wicket_check_fn is None:
            raise ValueError("WicketClient requires an injected wicket_check_fn")
        self._standing_client = standing_client
        self._wicket_check_fn = wicket_check_fn
        self._receipt_sink = receipt_sink

    def _emit_refusal_receipt(
        self,
        *,
        refusal_kind: str,
        detail: str,
        cooked_context: CookedContext,
        parent_receipt_id: Optional[str],
    ) -> Optional[str]:
        """Emit a wicket-seam refusal-time GateReceipt; return its id.

        Runtime invariant: refusal_kind MUST be in
        ``_WICKET_SEAM_REFUSAL_KINDS``. Returns None when no sink is
        wired. When ``parent_receipt_id`` is set (the standing-side
        receipt that caused this refusal), it is cited as the parent so
        ``governor why`` walks wicket → standing.
        """
        if refusal_kind not in _WICKET_SEAM_REFUSAL_KINDS:
            raise AssertionError(
                f"wicket_client attempted to emit refusal kind "
                f"{refusal_kind!r}, which is not in the closed set "
                f"{sorted(_WICKET_SEAM_REFUSAL_KINDS)}"
            )
        if self._receipt_sink is None:
            return None
        evidence_bundle: dict[str, Any] = {
            "refusal_kind": refusal_kind,
            "detail": detail,
            "actor": cooked_context.actor,
            "intended_action": cooked_context.intended_action,
            "target": cooked_context.target,
            "call_timestamp": cooked_context.call_timestamp,
            "parent_receipt_ids": (
                [parent_receipt_id] if parent_receipt_id else []
            ),
        }
        if cooked_context.standing_receipt_id is not None:
            evidence_bundle["cited_standing_receipt_id"] = (
                cooked_context.standing_receipt_id
            )
        # Subject bytes: a stable encoding of the cooked-context fields
        # that uniquely identify "what was checked" at this seam.
        subject_bytes = (
            f"{cooked_context.actor}|{cooked_context.intended_action}|"
            f"{cooked_context.target}|"
            f"{cooked_context.standing_receipt_id or ''}"
        ).encode("utf-8")
        receipt = self._receipt_sink.emit(
            gate=WICKET_SEAM_GATE,
            verdict="block",
            subject_kind="wicket_cooked_context",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S1_wicket", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id

    def _emit_admission_receipt(
        self,
        *,
        cooked_context: CookedContext,
        parent_receipt_id: Optional[str],
        downstream_verdict: Any,
    ) -> Optional[str]:
        """Emit a wicket-seam authorized-admission GateReceipt; return its id.

        D0c-a counterpart to ``_emit_refusal_receipt``. Verdict is "pass"
        — drawn from the closed positive-verdict vocabulary in
        GateReceiptSystem (``VALID_VERDICTS`` in ``gate_receipt.py``); no
        new verdict name invented. Returns None when no sink is wired
        (back-compat with D0a callers).

        ``parent_receipt_id`` is the verified standing receipt id, cited
        as the single parent in ``evidence_bundle.parent_receipt_ids`` —
        same chain shape D0a uses for refusals so ``governor why`` can
        walk wicket-admission → standing through real ids. When the
        standing client was constructed without a sink (verify still
        succeeds but no standing receipt is minted), ``parent_receipt_id``
        is None and the emitted admission receipt is a chain origin from
        AG's vantage.

        The wicket SPEC §7/§8 downstream verdict shape is opaque to this
        seam; we record a stable summary in the evidence bundle
        (downstream_verdict_repr) so the bundle is content-addressed and
        ``why`` can render the link. The closed-vocab refusal_kind field
        is deliberately omitted — this is a non-refusal receipt and
        ``why._classify`` correctly routes it to "non_refusal" / OK.
        """
        if self._receipt_sink is None:
            return None
        evidence_bundle: dict[str, Any] = {
            "admission_verdict": "authorized",
            "actor": cooked_context.actor,
            "intended_action": cooked_context.intended_action,
            "target": cooked_context.target,
            "call_timestamp": cooked_context.call_timestamp,
            "parent_receipt_ids": (
                [parent_receipt_id] if parent_receipt_id else []
            ),
            # repr() is stable enough for content addressing here; the
            # downstream verdict's canonical encoding is wicket's
            # responsibility, not the seam's.
            "downstream_verdict_repr": repr(downstream_verdict),
        }
        if cooked_context.standing_receipt_id is not None:
            evidence_bundle["cited_standing_receipt_id"] = (
                cooked_context.standing_receipt_id
            )
        subject_bytes = (
            f"{cooked_context.actor}|{cooked_context.intended_action}|"
            f"{cooked_context.target}|"
            f"{cooked_context.standing_receipt_id or ''}"
        ).encode("utf-8")
        receipt = self._receipt_sink.emit(
            gate=WICKET_SEAM_GATE,
            verdict=WICKET_SEAM_ADMIT_VERDICT,
            subject_kind="wicket_cooked_context",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S1_wicket", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id

    def check(
        self,
        cooked_context: CookedContext,
        *,
        finding_id: Optional[str] = None,
    ):
        """Run AG-side pre-call refusal, then route to wicket if clean.

        Returns:
            - ``WicketRefusal`` if standing_receipt_id is missing or
              dangling — and the injected wicket-check callable is NOT
              invoked. When a sink is wired, both the standing-side and
              wicket-side refusal receipts are minted; the WicketRefusal
              carries the wicket receipt id (and the parent standing id
              as ``parent_receipt_id``).
            - ``WicketVerdict`` wrapping the downstream verdict if the
              standing receipt verifies — the injected wicket-check
              callable is invoked exactly once with ``cooked_context``
              passed through verbatim.

        D0d-b: ``finding_id`` is the NQ-side chain origin (when the chain
        is driven by an NQ finding). It is plumbed into the standing
        client's ``verify(...)`` so the verified-standing receipt cites
        the finding as its parent; the admission receipt then cites the
        verified-standing receipt as its parent, making the
        finding → standing → admission chain walkable. ``None`` is
        accepted (CLI-originated or stub-driven chains have no NQ-side
        origin).
        """
        # AG-side pre-call refusal: standing receipt id must exist and
        # must be verifiable by the downstream standing service.
        try:
            self._standing_client.verify(
                cooked_context.standing_receipt_id,
                finding_id=finding_id,
            )
        except StandingRequiredError as e:
            wicket_rid = self._emit_refusal_receipt(
                refusal_kind=REFUSAL_KIND_STANDING_REQUIRED_LOCAL,
                detail=str(e),
                cooked_context=cooked_context,
                parent_receipt_id=e.receipt_id,
            )
            return WicketRefusal(
                refusal_kind=REFUSAL_KIND_STANDING_REQUIRED_LOCAL,
                detail=str(e),
                standing_receipt_id=None,
                receipt_id=wicket_rid,
                parent_receipt_id=e.receipt_id,
            )
        except DanglingStandingReceiptError as e:
            wicket_rid = self._emit_refusal_receipt(
                refusal_kind=REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE_LOCAL,
                detail=str(e),
                cooked_context=cooked_context,
                parent_receipt_id=e.receipt_id,
            )
            return WicketRefusal(
                refusal_kind=REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE_LOCAL,
                detail=str(e),
                standing_receipt_id=e.standing_receipt_id,
                receipt_id=wicket_rid,
                parent_receipt_id=e.receipt_id,
            )

        # Standing is verified — pass cooked context through to wicket.
        verdict = self._wicket_check_fn(cooked_context)
        # D0c-a: emit the authorized-admission receipt and propagate its
        # id onto the WicketVerdict so downstream callers (LA, the cooked
        # orchestrator) can carry it as ``admission_receipt_id`` and
        # ``governor why`` walks LA → wicket-admission through a real id.
        #
        # D0d-b: standing-success now mints its own verified-standing
        # GateReceipt (when a sink is wired on the standing client). The
        # standing receipt's id is exposed via the side-channel attribute
        # ``StandingClient._last_verified_receipt_id``; we cite it as
        # parent on the admission receipt so ``governor why`` walks
        # admission → standing-verification (→ NQ finding when a
        # ``finding_id`` was plumbed in). When the standing client was
        # constructed without a sink (back-compat), the side-channel is
        # ``None`` and the admission receipt is the chain origin from
        # AG's gate-receipt vantage — same behavior as D0c-a.
        verified_standing_rid = getattr(
            self._standing_client,
            "_last_verified_receipt_id",
            None,
        )
        admission_rid = self._emit_admission_receipt(
            cooked_context=cooked_context,
            parent_receipt_id=verified_standing_rid,
            downstream_verdict=verdict,
        )
        return WicketVerdict(
            value=verdict,
            receipt_id=admission_rid,
            parent_receipt_id=verified_standing_rid,
        )
