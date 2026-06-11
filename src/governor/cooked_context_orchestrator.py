# SPDX-License-Identifier: Apache-2.0
"""
Status: SPEC-honoring harness orchestrator (D0c-b)
Authority: composes existing D0a / D0c-a client seams; emits no new vocabulary
Promotion: stable when D0d harness lands; supersession requires D0c-b reopen

D0c-b: cooked-context orchestrator — assembles standing → wicket → LA in one
call path. Threads ``WicketVerdict.receipt_id`` into
``CookedCapacityRequest.admission_receipt_id``. Preserves the refusal vs
bypass distinction. Real receipt emission at every gate (no mocks for the
chain itself, only injected downstream callables per the existing seam
pattern).

Hard fence (operator-imposed, originally on D0c-b):

    D0c-b must remain origin-mode aware. AG-internal values (``cli_origin``,
    ``stub_origin``) label chains driven without an upstream NQ finding.
    NQ-side values are consumed verbatim from the NQ wire — AG does NOT
    invent or rename them.

Cross-repo bridge update (D0-Bridge, 2026-06-09):

    The NQ-side custody gap closed when NQ migration 057
    (``crates/nq-db/migrations/057_origin_mode_discriminator.sql``)
    landed an ``origin_mode`` discriminator on every ``FindingSnapshot``
    with the closed vocabulary
    ``{"observed", "drill", "replay", "synthetic"}``. AG's closed
    origin-mode set is now the union of AG-internal modes and the NQ-side
    modes; consumers of NQ wire DTOs feed the literal NQ value through.
    AG does NOT extend the NQ-side set unilaterally — any NQ vocabulary
    change requires a coordinated migration on both sides.

This module:

1. Defines the closed origin-mode set as the union of AG-internal and
   NQ-side vocabularies — ``{"cli_origin", "stub_origin"}`` (AG-minted)
   ∪ ``{"observed", "drill", "replay", "synthetic"}`` (NQ-minted). The
   orchestrator refuses to construct against any value outside the
   closed set, including umbrella aliases such as ``nq_origin`` — the
   bridge uses the concrete mint-provenance value, never an alias.

2. Wraps the caller-supplied ``ReceiptSink`` with a thin
   ``_OriginModeReceiptSink`` adapter that injects ``origin_mode`` into
   every emitted ``evidence_bundle`` at emit time. The existing clients
   (standing_client, wicket_client, linear_accountant_client) are NOT
   modified — they call ``sink.emit(...)`` exactly as today; the wrapped
   sink does the field injection en-route to the underlying sink.

3. Runs the chain. Standing receipt verification happens inside the
   wicket client (it composes a StandingClient internally per D0a).
   On any refusal at any seam, the orchestrator returns that refusal
   verbatim — the client's own ``_emit_refusal_receipt`` already minted
   the real GateReceipt; the orchestrator does not re-emit.
   On full success (wicket admits + LA grants + LA consumes), returns
   the LA ``ConsumedResult`` (effect allowed).

Origin-mode rendering through ``governor why`` is deliberately NOT touched
in this slice. ``why.py``'s render branch for ``origin_mode`` (DRILL prefix
etc.) is S5-NQ-origin work, gated on the NQ custody gap. For D0c-b it is
enough that ``origin_mode`` is *visible in the emitted evidence_bundle* and
would be there for a future renderer to pick up.

What this module deliberately does NOT do:

  * No invented NQ-shaped vocabulary. The NQ-side subset of the closed
    set is consumed verbatim from NQ's wire DTO
    (``FindingSnapshot.origin_mode``, NQ migration 057). AG does not add
    NQ values to the set without a corresponding NQ migration; AG does
    not rename or alias NQ values.
  * No GateReceipt schema change. ``evidence_bundle`` is an open dict;
    adding a key (``origin_mode``) is additive and does not touch the
    receipt envelope. Out: any change to GateReceipt fields, hash inputs,
    or VALID_VERDICTS.
  * No change to the closed S4-lite refusal-kind vocabulary or to
    ``BYPASS_BA3_FOR_MVP``. The micro-freeze stands.
  * No ``why.py`` modifications. Origin-mode render branch is S5-NQ-origin
    work, gated.
  * No D0d (compose harness) or D0e (show surface) work.
  * No D0-Origin / D0-Provenance work. Those are gated on the NQ-side
    custody gap (``working/nq-custody-gap-origin-discriminator.md``).
  * No BA3 surface modifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from governor.linear_accountant_client import (
    ConsumedResult,
    CookedCapacityRequest,
    CookedConsumeRequest,
    GrantedResult,
    LinearAccountantClient,
    ReceiptSink,
    RefusalResult,
)
from governor.wicket_client import (
    CookedContext,
    WicketClient,
    WicketRefusal,
    WicketVerdict,
)


# ---------------------------------------------------------------------------
# Closed origin-mode vocabulary.
#
# Two-axis composition:
#
#   * AG-internal modes — labels for chains driven from the AG-side CLI /
#     stubs without an upstream NQ finding.
#       - ``cli_origin``  : an operator invoked the chain at the CLI.
#       - ``stub_origin`` : a SPEC-honoring stub drove the chain (e.g.,
#                           orchestrator harness with no NQ in the loop).
#
#   * NQ-side modes — mint-provenance values consumed verbatim from NQ's
#     ``FindingSnapshot.origin_mode`` discriminator (migration 057,
#     ``crates/nq-db/migrations/057_origin_mode_discriminator.sql``). AG
#     does NOT invent or rename these values; the wire DTO is the bridge.
#       - ``observed``    : producer authentically observed the condition.
#       - ``drill``       : staged condition; fire drill with a real smoke
#                           machine. The condition is operator-staged, the
#                           producer's observation of the staged condition
#                           is still mechanical and real, but the chain of
#                           causation is operator-authored.
#       - ``replay``      : replayed from a prior real observation.
#       - ``synthetic``   : fully synthetic; no real condition exists.
#
# Adding a value to either axis requires explicit ratification:
#
#   * AG-internal: re-open D0c-b and document the new mode.
#   * NQ-side: requires a corresponding NQ migration extending the
#     ``origin_mode`` CHECK constraint AND an updated AG-side widening
#     here. Wire shape is the contract; AG never extends the NQ-side set
#     unilaterally.
# ---------------------------------------------------------------------------

# AG-internal origin modes.
ORIGIN_MODE_CLI = "cli_origin"
ORIGIN_MODE_STUB = "stub_origin"

# NQ-side origin modes (closed set defined by NQ migration 057). AG
# consumes these verbatim from ``FindingSnapshot.origin_mode``; no AG-side
# substitution, renaming, or inference.
ORIGIN_MODE_OBSERVED = "observed"
ORIGIN_MODE_DRILL = "drill"
ORIGIN_MODE_REPLAY = "replay"
ORIGIN_MODE_SYNTHETIC = "synthetic"

# AG-internal subset — modes that AG mints itself, not from NQ.
AG_INTERNAL_ORIGIN_MODES = frozenset({
    ORIGIN_MODE_CLI,
    ORIGIN_MODE_STUB,
})

# NQ-side subset — modes that originated as ``FindingSnapshot.origin_mode``
# on the NQ wire. The vocabulary is owned by NQ; this Python frozenset is
# AG's mirror for membership checks. If NQ adds a value, this set must be
# widened to match (and the cross-repo audit witness updated).
NQ_ORIGIN_MODES = frozenset({
    ORIGIN_MODE_OBSERVED,
    ORIGIN_MODE_DRILL,
    ORIGIN_MODE_REPLAY,
    ORIGIN_MODE_SYNTHETIC,
})

# Full closed set spanning both axes. Construction-time validation refuses
# any value not in this set. ``nq_origin`` (and other invented
# umbrella-shaped values) remain refused — the NQ-side bridge uses the
# concrete mint-provenance value (``observed``/``drill``/etc.), never an
# umbrella alias.
CLOSED_ORIGIN_MODES = AG_INTERNAL_ORIGIN_MODES | NQ_ORIGIN_MODES

# Evidence-bundle key the orchestrator stamps every emitted receipt with.
# Stable; downstream consumers (and a future origin-mode renderer in
# `why.py`) read this key. Not in any closed vocabulary set — it is a
# field name on the open evidence-bundle dict.
EVIDENCE_KEY_ORIGIN_MODE = "origin_mode"


class InvalidOriginModeError(ValueError):
    """Raised at orchestrator construction when ``origin_mode`` is not in
    ``CLOSED_ORIGIN_MODES``.

    This is the discipline-of-not-laundering test: passing ``nq_origin``
    (or any NQ-shaped value, or any other not-in-closed-set value) must
    refuse at construction, not silently propagate.
    """


# ---------------------------------------------------------------------------
# Operational-admission fence (simulated-evidence fence, ratified 2026-06-11).
#
# The closed vocabulary above answers "what KIND of provenance is this?".
# This fence answers the gate's one local question: "may a receipt bearing
# this origin satisfy an OPERATIONAL check — promote, suppress a real event,
# or become spendable?"  It is the missing enforcement: `origin_mode` was
# stamped and rendered (`why.py`), but nothing fenced operational consequence
# on it, so a synthetic/demo receipt could satisfy an operational check.
#
# Shape (ratified): closed-world ALLOWLIST, never a blocklist.  A blocklist
# ("refuse if synthetic") admits every novel value by default — a tool
# modified to emit `origin: test2` would sail through.  The allowlist admits
# iff the mode is in the ratified operational set; everything else refuses
# with a typed reason.  This mirrors the receipt-kernel (RKL) invariant:
# malformed aborts; unmodeled is never admitted; no projection turns unknown
# into accepted.
#
# Extension is a RATIFIED event, not an emergent default: widening
# OPERATIONAL_ORIGIN_MODES is a custody change (and MUST add a pinning-test
# case).  Gate-bearing rules never self-amend.
# ---------------------------------------------------------------------------

# The ONLY origin mode that permits operational consequence.  Strict by
# design: ``observed`` is the sole witnessed-from-the-world provenance.
# ``drill`` (operator-staged), ``replay`` (re-run of a past observation),
# ``synthetic`` (no real condition), ``cli_origin`` / ``stub_origin``
# (AG-internal, no upstream witness) are ALL non-operational.  Widening this
# set — e.g. if a real path needs ``cli_origin`` to be operational — is a
# one-line ratified change plus a pinning-test case, NEVER an inferred default.
OPERATIONAL_ORIGIN_MODES = frozenset({ORIGIN_MODE_OBSERVED})

# Typed admission outcomes.  A refusal is never a bare ``False`` — it carries
# its reason so the receipt names exactly which fantasy was denied admission.
ORIGIN_ADMITTED = "origin_admitted"
ORIGIN_REFUSED_NOT_OPERATIONAL = "origin_not_operational"
ORIGIN_REFUSED_UNRECOGNIZED = "origin_unrecognized"
ORIGIN_REFUSED_MISSING = "origin_missing"


class MalformedOriginError(TypeError):
    """``origin_mode`` present but not a string (tampered or mis-built
    bundle).  Malformed input ABORTS — it is never coerced into a refusal
    with an operational default, and never admitted."""


@dataclass(frozen=True)
class OriginAdmission:
    """Result of the operational-admission fence.

    Never a bare bool: a refusal carries its typed ``reason`` (one of the
    ``ORIGIN_*`` constants) and the offending ``origin_mode`` when there was
    one.  Callers branch on ``admitted``; audit reads ``reason``.
    """

    admitted: bool
    reason: str
    origin_mode: str | None

    @property
    def refused(self) -> bool:
        return not self.admitted


def operational_admission(origin_mode: object) -> OriginAdmission:
    """Closed-world fence: may a receipt bearing ``origin_mode`` satisfy an
    operational check (promote / suppress a real event / become spendable)?

    Decision table (allowlist, not blocklist)::

        None / absent                  -> refuse  ORIGIN_REFUSED_MISSING
        non-str                        -> raise   MalformedOriginError
        not in CLOSED_ORIGIN_MODES     -> refuse  ORIGIN_REFUSED_UNRECOGNIZED
        in CLOSED, not in OPERATIONAL  -> refuse  ORIGIN_REFUSED_NOT_OPERATIONAL
        in OPERATIONAL_ORIGIN_MODES    -> admit

    A novel origin string (a tool emitting an unmodeled value) lands in
    ORIGIN_REFUSED_UNRECOGNIZED — never in admission.  Missing is treated as
    malformed-for-operational-purposes (refused), never defaulted to
    operational.  This is the fence's whole point.
    """
    if origin_mode is None:
        return OriginAdmission(False, ORIGIN_REFUSED_MISSING, None)
    if not isinstance(origin_mode, str):
        raise MalformedOriginError(
            f"origin_mode must be a string, got {type(origin_mode).__name__}"
        )
    if origin_mode not in CLOSED_ORIGIN_MODES:
        return OriginAdmission(False, ORIGIN_REFUSED_UNRECOGNIZED, origin_mode)
    if origin_mode not in OPERATIONAL_ORIGIN_MODES:
        return OriginAdmission(False, ORIGIN_REFUSED_NOT_OPERATIONAL, origin_mode)
    return OriginAdmission(True, ORIGIN_ADMITTED, origin_mode)


def operational_admission_for_bundle(
    evidence_bundle: dict[str, Any] | None,
) -> OriginAdmission:
    """Run the fence against a receipt's evidence bundle.

    Reads ``evidence_bundle[EVIDENCE_KEY_ORIGIN_MODE]``.  A missing bundle or
    a bundle without the key refuses with ORIGIN_REFUSED_MISSING — an
    unstamped receipt has no attested origin and so cannot be operational.
    """
    if not evidence_bundle:
        return OriginAdmission(False, ORIGIN_REFUSED_MISSING, None)
    return operational_admission(evidence_bundle.get(EVIDENCE_KEY_ORIGIN_MODE))


# ---------------------------------------------------------------------------
# Receipt-sink wrapper.
#
# Thin adapter that injects ``origin_mode`` into every emitted
# evidence_bundle at emit time. The existing standing/wicket/LA clients
# are NOT modified — they call ``sink.emit(...)`` exactly as today; this
# wrapper does the field injection en-route.
# ---------------------------------------------------------------------------


class _OriginModeReceiptSink:
    """Wraps a ReceiptSink and stamps ``origin_mode`` onto every emit.

    Duck-typed match to the ``ReceiptSink`` Protocol declared in the three
    client modules: ``emit(gate, verdict, subject_kind, subject_bytes,
    evidence_bundle, gate_config, **kwargs) -> GateReceipt``.

    Injection rule:

      * ``evidence_bundle`` is shallow-copied (the caller's dict is not
        mutated); ``origin_mode`` is set on the copy.
      * If the caller already supplied an ``origin_mode`` key, the wrapper
        OVERWRITES it. The orchestrator is authoritative for this field;
        a client that wants to set ``origin_mode`` itself should not — the
        orchestrator owns the labeling.

    The wrapped sink is the only path through which the orchestrator-
    coordinated chain emits receipts, so every receipt minted on the chain
    carries the orchestrator's declared ``origin_mode``.
    """

    def __init__(self, inner_sink: ReceiptSink, origin_mode: str):
        if origin_mode not in CLOSED_ORIGIN_MODES:
            # Defense-in-depth: the orchestrator validates origin_mode at
            # construction, but if anyone constructs the wrapper directly
            # with a bad value, refuse here too.
            raise InvalidOriginModeError(
                f"origin_mode {origin_mode!r} not in closed set "
                f"{sorted(CLOSED_ORIGIN_MODES)}"
            )
        self._inner = inner_sink
        self._origin_mode = origin_mode

    def emit(
        self,
        gate: str,
        verdict: str,
        subject_kind: str,
        subject_bytes: bytes,
        evidence_bundle: dict[str, Any],
        gate_config: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        stamped = dict(evidence_bundle)  # shallow copy — do not mutate caller
        stamped[EVIDENCE_KEY_ORIGIN_MODE] = self._origin_mode
        return self._inner.emit(
            gate=gate,
            verdict=verdict,
            subject_kind=subject_kind,
            subject_bytes=subject_bytes,
            evidence_bundle=stamped,
            gate_config=gate_config,
            **kwargs,
        )


def wrap_receipt_sink_with_origin_mode(
    sink: ReceiptSink, origin_mode: str
) -> _OriginModeReceiptSink:
    """Public helper: wrap a ReceiptSink so it stamps ``origin_mode`` on emits.

    Callers building the three client seams pass the wrapped sink to each
    client's constructor; the clients then emit receipts that carry
    ``evidence_bundle["origin_mode"]`` without any client-side change.

    This is the recommended wiring path when an orchestrator instance is
    not used (e.g., a future demo harness that wants origin-mode labeling
    without going through the orchestrator).
    """
    return _OriginModeReceiptSink(sink, origin_mode)


# ---------------------------------------------------------------------------
# Result type — a tiny ADT over WicketRefusal | RefusalResult | ConsumedResult.
#
# ChainResult carries which seam fired (so the caller can render the
# refusal at the right gate) and the underlying client result verbatim.
# Refusals are NOT re-wrapped; the orchestrator returns the client's own
# result so callers and tests see the exact same shape they would see
# without the orchestrator.
# ---------------------------------------------------------------------------


# Seam tags — stable; mirror the gate names the clients emit under.
SEAM_WICKET = "wicket_seam"
SEAM_LA_REQUEST = "la_seam_request"
SEAM_LA_CONSUME = "la_seam_consume"


# ---------------------------------------------------------------------------
# Operational-consequence type split (Wall 1 of the simulated-evidence fence,
# ratified 2026-06-12).
#
# A successful chain produces ONE OF TWO DISTINCT TYPES — never one type with
# a boolean rider. The discriminator is `origin_mode`, which the orchestrator
# owns (the LA seam never sees it). Two claims that the house rule forbids
# sharing a type, because there is a scenario that attests one and refuses the
# other:
#
#   * ``consumed``    — the machinery ran: exactly-once consume happened,
#                       receipts minted, chain walkable. TRUE for a drill.
#   * ``operational`` — the consume may confer real-world consequence
#                       (spend real capacity, suppress a real event, promote).
#                       FALSE for a drill.
#
# So: ``OperationalConsumed`` (origin admitted — ``observed``) and
# ``DemonstratedConsumed`` (origin non-operational — drill / synthetic /
# replay / cli_origin / stub_origin) are different types. Only the former is
# accepted by ``confer_operational_effect`` (the single spend/effect seam).
#
# Why a type split and not a ``.operational`` flag: a flag is a vigilance
# discipline — "downstream MUST remember to check it" — which is the blocklist
# pattern wearing a flag costume. One forgetful consumer confers real effect
# from a drill. The type split makes that construction UNREPRESENTABLE: a
# ``DemonstratedConsumed`` cannot pass the spend wall's ``isinstance`` gate, so
# downstream does not check — it *cannot misuse*. Promises are testimony;
# walls are walls. (Python types vanish at runtime, so the wall ships WITH a
# runtime ``isinstance`` check and a negative pinning test, or it is theatre.)
#
# Both wrap the underlying LA ``ConsumedResult`` (reach it via
# ``consumed_result`` for transcript / proposal-packet / ``governor why``
# chain walking — those are *demonstration* reads, not spends, and are
# legitimate on either type). ``origin_admission`` is the fence verdict.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationalConsumed:
    """Chain completed under an OPERATIONAL origin (``origin_mode=observed``).

    The ONLY chain outcome that :func:`confer_operational_effect` accepts.
    ``origin_admission.admitted`` is ``True``. Wraps the LA ``ConsumedResult``
    so transcript / proposal-packet code can reach the token id and receipt
    ids via ``consumed_result``.
    """

    consumed_result: ConsumedResult
    origin_admission: OriginAdmission


@dataclass(frozen=True)
class DemonstratedConsumed:
    """Chain MECHANICALLY completed under a NON-operational origin
    (``drill`` / ``synthetic`` / ``replay`` / ``cli_origin`` / ``stub_origin``).

    The machinery ran for real — exactly-once consume against *simulated*
    capacity, receipts minted, chain walkable — so this is a genuine
    demonstration of structure (zoning §Evidence classes: "simulated may
    demonstrate structure / test machinery"). What it may NOT do is confer
    operational consequence: it is a DISTINCT type from
    :class:`OperationalConsumed`, and :func:`confer_operational_effect` refuses
    it at the wall. ``origin_admission`` carries the typed refusal
    (``admitted`` is ``False``; ``reason`` is ``origin_not_operational``).
    """

    consumed_result: ConsumedResult
    origin_admission: OriginAdmission


class NonOperationalSpendError(Exception):
    """A non-operational chain outcome reached the spend / effect interface.

    The structural fence: only an :class:`OperationalConsumed` may confer
    operational effect. A :class:`DemonstratedConsumed` (drill / synthetic /
    replay / cli / stub origin), a bare ``ConsumedResult`` (no origin verdict
    attached), a refusal, or ``None`` is refused HERE — not by a flag a caller
    must remember to check, but by the type wall. Carries the offending
    ``origin_mode`` / ``reason`` when available so the refusal names which
    fantasy was denied a spend.
    """

    def __init__(
        self,
        message: str,
        *,
        origin_mode: str | None = None,
        reason: str | None = None,
    ):
        super().__init__(message)
        self.origin_mode = origin_mode
        self.reason = reason


def confer_operational_effect(outcome: object) -> ConsumedResult:
    """The single operational spend / effect-conferring seam (Wall 1).

    Accepts ONLY :class:`OperationalConsumed` and returns the underlying
    ``ConsumedResult`` the caller may now act on (spend the capacity, apply
    the effect, suppress the real event). Everything else — a
    :class:`DemonstratedConsumed`, a raw ``ConsumedResult``, a refusal,
    ``None`` — raises :class:`NonOperationalSpendError`.

    Conferring operational effect from a non-operational origin is not
    *guarded* here, it is made *unrepresentable*: callers do not inspect
    ``.operational``; they pass the chain outcome through this seam and either
    receive a spendable ``ConsumedResult`` or a raised refusal. Any future
    spend/effect path MUST route through this function — that is what makes the
    fence arithmetic instead of vigilance.
    """
    if isinstance(outcome, OperationalConsumed):
        return outcome.consumed_result
    if isinstance(outcome, DemonstratedConsumed):
        raise NonOperationalSpendError(
            "refusing operational effect: chain outcome is "
            f"DemonstratedConsumed (origin_mode="
            f"{outcome.origin_admission.origin_mode!r}, reason="
            f"{outcome.origin_admission.reason!r}). Only an OperationalConsumed "
            "(origin_mode=observed) may confer operational effect.",
            origin_mode=outcome.origin_admission.origin_mode,
            reason=outcome.origin_admission.reason,
        )
    raise NonOperationalSpendError(
        "refusing operational effect: expected OperationalConsumed, got "
        f"{type(outcome).__name__}. A bare ConsumedResult carries no origin "
        "verdict and is not spendable; route chain outcomes through the "
        "orchestrator so the operational-admission fence applies."
    )


@dataclass(frozen=True)
class ChainResult:
    """The result of running the cooked-context chain.

    ``outcome`` is the verbatim client result, or — on full success — the
    operational-consequence type split:

      * ``WicketRefusal`` — wicket-seam refused (missing/dangling
        standing receipt id). LA was not invoked.
      * ``RefusalResult`` — LA seam refused (admission gate or capacity
        decision or consume failure). The ``seam`` field disambiguates
        whether the refusal happened at request-capacity or consume.
      * ``OperationalConsumed`` — full chain succeeded AND the origin is
        operational (``observed``): the effect may be conferred.
      * ``DemonstratedConsumed`` — full chain succeeded mechanically but
        the origin is non-operational (drill/synthetic/replay/cli/stub):
        structure demonstrated, effect fenced.

    ``seam`` names the gate that produced the outcome. Stable across the
    chain; used by a future renderer (or harness assertion) to know
    which gate fired without re-classifying.
    """

    outcome: (
        WicketRefusal | RefusalResult | OperationalConsumed | DemonstratedConsumed
    )
    seam: str

    @property
    def refused(self) -> bool:
        return isinstance(self.outcome, (WicketRefusal, RefusalResult))

    @property
    def consumed(self) -> bool:
        """The chain MECHANICALLY consumed (operational OR demonstrated).

        Structure-completion, NOT permission to confer effect. A drill chain
        is ``consumed`` (the machinery ran) but not ``operational``. Read
        ``operational``, or hand the outcome to
        :func:`confer_operational_effect`, before conferring any real effect.
        """
        return isinstance(
            self.outcome, (OperationalConsumed, DemonstratedConsumed)
        )

    @property
    def operational(self) -> bool:
        """The chain consumed under an operational origin — the outcome may
        confer operational effect. Distinct from ``consumed``: a drill chain
        is ``consumed`` but not ``operational``."""
        return isinstance(self.outcome, OperationalConsumed)


# ---------------------------------------------------------------------------
# The orchestrator.
# ---------------------------------------------------------------------------


class CookedContextOrchestrator:
    """Composes standing → wicket → LA in one call path.

    Constructor takes the three pre-constructed clients and an explicit
    ``origin_mode``. The clients are expected to have been built with a
    sink wrapped by ``wrap_receipt_sink_with_origin_mode`` so that every
    receipt emitted during ``run()`` carries the origin-mode stamp; the
    orchestrator does not re-wire the sinks itself (that would require
    construction-time access to the underlying sink which the clients
    deliberately hide). The wiring is the caller's responsibility — see
    the build helper ``build_chain_clients`` below for the canonical
    wiring pattern.

    ``run(cooked_context, capacity_request_template, consume_request_template,
          now)`` drives the chain:

      1. ``wicket_client.check(cooked_context)`` — pre-call standing
         verification + wicket-check downstream.
      2. If wicket returned a verdict (not a refusal), threads
         ``verdict.receipt_id`` into ``capacity_request_template`` as
         ``admission_receipt_id`` (the template's existing
         ``admission_receipt_id`` is REPLACED — the orchestrator is
         authoritative for that field's value).
      3. ``la_client.request_capacity(...)`` — pre-call admission
         verification + LA request.
      4. If granted, builds the consume request with the granted
         ``token_id`` and calls ``la_client.consume(...)``.

    Refusal at any step returns the client's result verbatim wrapped in a
    ``ChainResult`` naming the seam. Success returns the ``ConsumedResult``
    wrapped in a ``ChainResult`` with ``seam == SEAM_LA_CONSUME``.

    The orchestrator does not emit its own receipts. Every receipt on the
    chain was minted by one of the three clients, through the wrapped
    sink, so each one carries the ``origin_mode`` stamp in its
    ``evidence_bundle``.
    """

    def __init__(
        self,
        wicket_client: WicketClient,
        la_client: LinearAccountantClient,
        origin_mode: str,
    ):
        if origin_mode not in CLOSED_ORIGIN_MODES:
            raise InvalidOriginModeError(
                f"origin_mode {origin_mode!r} is not in the closed set "
                f"{sorted(CLOSED_ORIGIN_MODES)}. AG-internal values are "
                f"{sorted(AG_INTERNAL_ORIGIN_MODES)}; NQ-side values are "
                f"{sorted(NQ_ORIGIN_MODES)} (consumed verbatim from "
                f"FindingSnapshot.origin_mode per NQ migration 057). "
                f"Umbrella-shaped values such as 'nq_origin' remain "
                f"refused — the bridge uses the concrete mint-provenance "
                f"value, never an alias."
            )
        if wicket_client is None:
            raise ValueError(
                "CookedContextOrchestrator requires a WicketClient"
            )
        if la_client is None:
            raise ValueError(
                "CookedContextOrchestrator requires a LinearAccountantClient"
            )
        self._wicket = wicket_client
        self._la = la_client
        self._origin_mode = origin_mode

    @property
    def origin_mode(self) -> str:
        """The closed-set origin-mode this orchestrator labels receipts with."""
        return self._origin_mode

    def run(
        self,
        cooked_context: CookedContext,
        capacity_request_template: CookedCapacityRequest,
        consume_request_template: CookedConsumeRequest,
        now: int,
        *,
        finding_id: Optional[str] = None,
    ) -> ChainResult:
        """Drive standing → wicket → LA-request → LA-consume.

        Refusal at any seam short-circuits — the next stage is NEVER
        invoked. The returned ``ChainResult.outcome`` is the verbatim
        refusal from the client that produced it; the orchestrator does
        not re-wrap or re-classify. Receipts at each seam were minted by
        the client's own emission helper through the wrapped sink, so
        each carries ``evidence_bundle["origin_mode"]``.

        D0d-b: ``finding_id`` is the NQ-side chain origin (when the
        chain is driven by an NQ finding). It is plumbed into the
        wicket client's ``check(...)`` which in turn plumbs it into
        ``StandingClient.verify(...)`` so the verified-standing receipt
        cites the finding as its parent. The orchestrator also threads
        each minted positive receipt's id into the next stage's parent
        linkage so the chain walks finding → standing → admission →
        granted → consumed end-to-end.

        On full success returns ``ChainResult(outcome=ConsumedResult,
        seam=SEAM_LA_CONSUME)``.
        """
        # Step 1: wicket (includes standing verification inside).
        # D0d-b: thread finding_id so the standing receipt cites it as
        # parent and the admission receipt cites the standing receipt
        # as parent (wicket reads the standing-side last-verified id
        # off the standing client's side channel).
        wicket_result = self._wicket.check(
            cooked_context, finding_id=finding_id
        )
        if isinstance(wicket_result, WicketRefusal):
            return ChainResult(outcome=wicket_result, seam=SEAM_WICKET)

        # WicketVerdict carries the authorized-admission receipt id
        # (per D0c-a). Thread it into the capacity request as
        # admission_receipt_id, replacing the template's value.
        assert isinstance(wicket_result, WicketVerdict)
        admission_receipt_id = wicket_result.receipt_id

        capacity_request = _replace_admission_receipt_id(
            capacity_request_template, admission_receipt_id
        )

        # Step 2: LA request_capacity. Refusal short-circuits.
        # D0d-b: the LA client emits a granted GateReceipt citing the
        # admission_receipt_id as parent (via the request's
        # admission_receipt_id field — verified before emission).
        capacity_result = self._la.request_capacity(capacity_request, now)
        if isinstance(capacity_result, RefusalResult):
            return ChainResult(outcome=capacity_result, seam=SEAM_LA_REQUEST)

        assert isinstance(capacity_result, GrantedResult)

        # Step 3: LA consume. Re-bind the consume request to use the
        # granted token_id; everything else from the template.
        # D0d-b: thread the granted receipt id so the consume receipt
        # cites it as parent — closing the four-link chain.
        consume_request = _replace_token_id(
            consume_request_template, capacity_result.token_id
        )

        consume_result = self._la.consume(
            consume_request,
            now,
            parent_grant_receipt_id=capacity_result.receipt_id,
        )
        if isinstance(consume_result, RefusalResult):
            return ChainResult(outcome=consume_result, seam=SEAM_LA_CONSUME)

        assert isinstance(consume_result, ConsumedResult)

        # Operational-consequence fence (Wall 1). The chain mechanically
        # consumed; whether that consume may confer OPERATIONAL effect depends
        # on this orchestrator's declared origin_mode. ``observed`` →
        # OperationalConsumed (spendable); every other closed-set mode (drill /
        # synthetic / replay / cli_origin / stub_origin) → DemonstratedConsumed
        # (structure shown, effect fenced by type). origin_mode is validated
        # in __init__ to be in CLOSED_ORIGIN_MODES, so the fence never sees
        # MISSING / UNRECOGNIZED / malformed here — only admitted-vs-not.
        admission = operational_admission(self._origin_mode)
        outcome: OperationalConsumed | DemonstratedConsumed
        if admission.admitted:
            outcome = OperationalConsumed(
                consumed_result=consume_result, origin_admission=admission
            )
        else:
            outcome = DemonstratedConsumed(
                consumed_result=consume_result, origin_admission=admission
            )
        return ChainResult(outcome=outcome, seam=SEAM_LA_CONSUME)


# ---------------------------------------------------------------------------
# Small frozen-dataclass field replacements.
#
# CookedCapacityRequest and CookedConsumeRequest are frozen; we can't
# mutate the templates the caller hands us. These helpers build a fresh
# instance with one field replaced. Kept private — callers should not
# need to construct these themselves.
# ---------------------------------------------------------------------------


def _replace_admission_receipt_id(
    template: CookedCapacityRequest,
    admission_receipt_id: Optional[str],
) -> CookedCapacityRequest:
    return CookedCapacityRequest(
        request_id=template.request_id,
        actor=template.actor,
        action=template.action,
        target=template.target,
        scope=template.scope,
        requested_capacity=template.requested_capacity,
        admission_receipt_id=admission_receipt_id,
        eligibility_valid_until=template.eligibility_valid_until,
        expires_after=template.expires_after,
        idempotency_key=template.idempotency_key,
    )


def _replace_token_id(
    template: CookedConsumeRequest,
    token_id: Any,
) -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id=template.consumption_event_id,
        token_id=token_id,
        actor=template.actor,
        action=template.action,
        target=template.target,
        amount=template.amount,
        scope=template.scope,
    )
