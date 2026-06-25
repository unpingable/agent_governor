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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable, Optional

from governor.linear_accountant_client import (
    ConsumedResult,
    CookedCapacityRequest,
    CookedConsumeRequest,
    GrantedResult,
    LinearAccountantClient,
    ReceiptSink,
    RefusalResult,
)
from governor.standing_spendability import (
    SpendabilityRefusal,
    StandingSpendabilityGate,
    StandingWindow,
)
from governor.playbooks.admission_evidence import PlaybookAdmissionEvidence
from governor.wicket_client import (
    WICKET_SEAM_ADMIT_VERDICT,
    WICKET_SEAM_GATE,
    CookedContext,
    WicketClient,
    WicketRefusal,
    WicketVerdict,
)
from governor.gate_receipt import canonical_json, content_hash
from governor.pipeline_types import (
    DISPOSITION_COMPLETED,
    DISPOSITION_REFUSED,
    VERDICT_REFUSED_LAUNDERING,
    BoundaryAccounting,
    RecompositionReceipt,
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
SEAM_STANDING_SPENDABILITY = "standing_spendability_seam"
SEAM_LA_REQUEST = "la_seam_request"
SEAM_LA_CONSUME = "la_seam_consume"
# Recomposition is not a chain seam (no client, no spend). It is the
# post-chain legitimacy gate: it may refuse a would-be-admissible chain whose
# recomposition launders a dropped boundary. Its only verb is "refuse".
SEAM_RECOMPOSITION = "recomposition_seam"


# ---------------------------------------------------------------------------
# Authority-admission-basis wall (Slice 4 — playbook-governed spend).
#
# The LA spend's basis MUST be an *authority* receipt — the wicket-seam
# admission (verdict="pass") that Standing authorized — NEVER the
# playbook-evidence record (gate="wicket_playbook_evidence", verdict="observe")
# that merely recorded the certification. Both resolve in the receipt store, so
# "does the cited id resolve?" is not enough: a caller could cite the observe
# record and a resolve-only verifier would wave it through. That is the Slice 4
# laundering vector — certification masquerading as a spend basis.
#
# This wall makes the distinction mechanical: a cited admission id is a valid
# spend basis IFF it resolves to a wicket-seam pass admission. The orchestrator
# never offers the observe id to LA (it threads the WicketVerdict's receipt_id,
# which is always the pass admission), so the happy path is correct by
# construction; this verifier is the defense-in-depth that refuses a *manual*
# attempt to spend against an evidence record.
# ---------------------------------------------------------------------------


def is_authority_admission_receipt(receipt: object) -> bool:
    """True iff ``receipt`` is a wicket-seam authority admission (verdict=pass).

    The observe-verdict playbook-evidence record (gate
    ``wicket_playbook_evidence``) returns False: evidence is not authority, so
    it is not a spend basis. Defensive against None / receipts missing the
    attributes.
    """
    return (
        receipt is not None
        and getattr(receipt, "gate", None) == WICKET_SEAM_GATE
        and getattr(receipt, "verdict", None) == WICKET_SEAM_ADMIT_VERDICT
    )


def build_authority_admission_verifier(sink: Any) -> Callable[[str], bool]:
    """An LA ``admission_verifier`` that admits ONLY authority receipts.

    Pass the result as ``LinearAccountantClient(admission_verifier=...)`` for a
    playbook-governed spend chain. It resolves the cited id through the sink's
    receipt store and accepts it only when it is a wicket-seam pass admission —
    so an observe-verdict evidence record cited as a spend basis is refused
    (LA returns ``dangling_receipt_reference``: there is no *admission* at that
    id, even though some receipt resolves there).

    ``sink`` must expose ``receipt_store.get_by_id``; this is the unwrapped
    ``GateReceiptSystem`` (not the origin-mode wrapper, which has no store).
    """
    def verify(admission_receipt_id: str) -> bool:
        receipt = sink.receipt_store.get_by_id(admission_receipt_id)
        return is_authority_admission_receipt(receipt)

    return verify


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
class RecompositionRefusal:
    """A would-be-admissible chain refused at recomposition because its declared
    decomposition launders a dropped boundary (``refused_laundering``).

    P3.2 enforcement. Recomposition *stops the train; it does not choose the
    destination* — so this type deliberately does NOT carry the laundered success
    outcome. The train stops; the cargo is not forwarded. Downstream sees a
    refusal (``ChainResult.refused`` is ``True``) and the diagnosis (which admitted
    boundaries went unaccounted), never the consumed result. The effective
    :class:`RecompositionReceipt` is the walkable record of why.

    It is NOT a spend, mutation, retry, or alternative path: enforcement only
    converts a launderable success into this refusal. ``confer_operational_effect``
    rejects it at the type wall, same as any other non-``OperationalConsumed``.
    """

    receipt: RecompositionReceipt
    accounting: BoundaryAccounting


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
      * ``SpendabilityRefusal`` — standing-spendability seam refused: the
        standing observation lapsed past its horizon by exercise time.
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
        WicketRefusal
        | SpendabilityRefusal
        | RefusalResult
        | RecompositionRefusal
        | OperationalConsumed
        | DemonstratedConsumed
    )
    seam: str

    @property
    def refused(self) -> bool:
        return isinstance(
            self.outcome,
            (
                WicketRefusal,
                SpendabilityRefusal,
                RefusalResult,
                RecompositionRefusal,
            ),
        )

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
# Shadow recomposition (P1.2 — workflow-kernel campaign,
# specs/gaps/GOV_GAP_RECOMPOSITION_RECEIPT_001.md).
#
# A Geiger counter, not a courthouse. Given a ChainResult, derive a SHADOW
# (effective=False) RecompositionReceipt recording the boundary-accounting
# verdict the cooked-context chain WOULD render. Because the chain is
# sequential and accounts every boundary it traverses, a real run reads
# ``admissible`` (full consume) or ``refused_carried`` (any refusal) — never
# ``refused_laundering``. That alarm is reserved for a decomposition whose
# admitted boundaries genuinely go missing; the orchestrator never manufactures
# one, so the shadow verdict looking "boring" is the instrument working.
#
# Pure: no IO, no client calls, no effect. Wired into run() behind an opt-in
# sink that defaults off, so the chain's behavior is byte-identical without it.
# ---------------------------------------------------------------------------

RecompositionSink = Callable[[RecompositionReceipt], None]

# The cooked-context chain's boundaries, in traversal order. The optional
# standing-spendability gate is asserted as a traversed boundary ONLY when it is
# the seam that fired — we cannot prove it ran otherwise, so the shadow
# accounting never fabricates a boundary the ChainResult does not witness.
_CHAIN_SEAM_ORDER: tuple[str, ...] = (
    SEAM_WICKET,
    SEAM_STANDING_SPENDABILITY,
    SEAM_LA_REQUEST,
    SEAM_LA_CONSUME,
)

_RECOMPOSITION_KERNEL = "workflow:cooked_context (provisional)"


def _collect_chain_receipt_ids(outcome: object) -> tuple[str, ...]:
    """Best-effort gather of receipt ids the ChainResult witnesses.

    Every outcome type carries an optional ``receipt_id``; the consumed types
    nest one (and its parent) on ``consumed_result``. Missing ids are skipped —
    references are carried "as available", never fabricated.
    """
    ids: list[str] = []
    direct = getattr(outcome, "receipt_id", None)
    if isinstance(direct, str) and direct:
        ids.append(direct)
    consumed = getattr(outcome, "consumed_result", None)
    if consumed is not None:
        for attr in ("receipt_id", "parent_receipt_id"):
            value = getattr(consumed, attr, None)
            if isinstance(value, str) and value:
                ids.append(value)
    return tuple(dict.fromkeys(ids))  # de-dupe, preserve order


def _chain_traversal(chain_result: ChainResult) -> tuple[list[str], dict[str, str]]:
    """The boundaries the chain PROVABLY traversed and their dispositions.

    Canonical seams up to and including the firing seam (skipping the optional
    spendability gate unless it IS the firing seam); each completed, except a
    refused firing seam which is dispositioned ``refused``. This is the chain's
    own self-accounting — never fabricates a boundary the ChainResult does not
    witness. Shared by the shadow observer and the enforcing gate so both agree
    on what "the chain accounted" means.
    """
    seam = chain_result.seam
    admitted: list[str] = []
    for boundary in _CHAIN_SEAM_ORDER:
        if (
            boundary == SEAM_STANDING_SPENDABILITY
            and seam != SEAM_STANDING_SPENDABILITY
        ):
            continue
        admitted.append(boundary)
        if boundary == seam:
            break

    accounted = {boundary: DISPOSITION_COMPLETED for boundary in admitted}
    if chain_result.refused and seam in accounted:
        accounted[seam] = DISPOSITION_REFUSED
    return admitted, accounted


def _chain_recomposition_meta(
    chain_result: ChainResult, origin_mode: str
) -> dict[str, Any]:
    """The non-boundary receipt fields derived from the chain (basis, kernel,
    spend summary, source ids). Shared so shadow and enforcing receipts carry
    identical provenance — they differ ONLY in admitted set and shadow/effective.
    """
    seam = chain_result.seam
    source_receipt_ids = _collect_chain_receipt_ids(chain_result.outcome)

    # No projected intent yet (intent_compiler fidelity lands in P1.4). Until
    # then the receipt's basis reference is a content-addressed fingerprint of
    # the chain's own identity (seam + witnessed receipts), NOT an intent. P1.4
    # supplies the real projected_intent_hash.
    basis = content_hash(
        canonical_json(
            {
                "basis": "cooked_context_chain",
                "seam": seam,
                "source_receipt_ids": sorted(source_receipt_ids),
            }
        )
    )
    reached_la = seam in (SEAM_LA_REQUEST, SEAM_LA_CONSUME)
    return {
        "projected_intent_hash": "sha256:" + basis,
        "accepted_by_kernel": _RECOMPOSITION_KERNEL,
        "la_spend": {
            "seam": seam,
            "origin_mode": origin_mode,
            # Origin fence, where available: OperationalConsumed only.
            "origin_admitted": str(chain_result.operational).lower(),
            "consumed": str(chain_result.consumed).lower(),
        },
        # LA-backed iff the chain reached LA; a pre-LA refusal spent nothing
        # through LA, and the downgrade is visible rather than faked.
        "la_custody": reached_la,
        "source_receipt_ids": source_receipt_ids,
    }


def shadow_recomposition(
    chain_result: ChainResult, *, origin_mode: str
) -> RecompositionReceipt:
    """Map a ChainResult to a SHADOW RecompositionReceipt (effective=False).

    See the module section header above. Pure; the returned receipt
    blocks/gates/retries nothing and is advisory only. The admitted set is the
    chain's own traversal, so a sequential chain reads ``admissible`` /
    ``refused_carried`` and never organically ``refused_laundering``.
    """
    admitted, accounted = _chain_traversal(chain_result)
    return RecompositionReceipt.from_boundaries(
        admitted=admitted,
        accounted=accounted,
        shadow=True,
        effective=False,
        **_chain_recomposition_meta(chain_result, origin_mode),
    )


def enforce_recomposition(
    chain_result: ChainResult,
    *,
    origin_mode: str,
    recomposition_plan: Sequence[str],
) -> RecompositionReceipt:
    """Build an EFFECTIVE RecompositionReceipt accounting the DECLARED
    decomposition plan against what the chain actually traversed.

    The admitted set is the caller's declared decomposition (the boundaries the
    decompose step committed to). The accounted set is the chain's own
    traversal. A declared boundary the chain never accounted is a silently
    dropped slice — :func:`account_boundaries` renders ``refused_laundering``,
    and the receipt carries that verdict (its integrity invariant recomputes it,
    so the verdict cannot be hand-set). This function is PURE: it builds a record
    and renders a verdict; it performs no IO, no client calls, no mutation, and
    decides no alternative. The orchestrator decides what to do with a laundering
    verdict — and its only option is to refuse.
    """
    _, accounted = _chain_traversal(chain_result)
    return RecompositionReceipt.from_boundaries(
        admitted=list(recomposition_plan),
        accounted=accounted,
        shadow=False,
        effective=True,
        **_chain_recomposition_meta(chain_result, origin_mode),
    )


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
    chain was minted by one of the seam clients/gates (standing, wicket, the
    optional standing-spendability gate, LA), through the wrapped sink, so each
    one carries the ``origin_mode`` stamp in its ``evidence_bundle``.

    The optional ``standing_spendability_gate`` is composed at the
    standing->spendability edge (post-admission, pre-spend). When present AND a
    ``standing_window`` is passed to ``run()``, the gate checks whether the
    standing observation is still within its freshness horizon at exercise
    time; a lapse short-circuits the chain before any capacity is spent. When
    absent (the default), the chain runs exactly as before.
    """

    def __init__(
        self,
        wicket_client: WicketClient,
        la_client: LinearAccountantClient,
        origin_mode: str,
        *,
        standing_spendability_gate: Optional[StandingSpendabilityGate] = None,
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
        self._spendability_gate = standing_spendability_gate

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
        standing_window: Optional[StandingWindow] = None,
        playbook_evidence: Optional[PlaybookAdmissionEvidence] = None,
        recomposition_sink: Optional[RecompositionSink] = None,
        recomposition_plan: Optional[Sequence[str]] = None,
    ) -> ChainResult:
        """Drive the cooked-context chain; see :meth:`_run_chain` for the steps.

        ``playbook_evidence`` (Slice 4) opts the chain into playbook-governed
        admission: when supplied, step 1 routes through
        ``WicketClient.check_playbook_admission`` (evidence coherence → Standing
        authority) instead of the bare ``check``. Evidence coherence is a
        necessary precondition that refuses *before* Standing; it never becomes
        the spend basis — the LA request is still threaded the authority (pass)
        admission receipt, never the observe evidence record. When ``None`` (the
        default) the chain is byte-identical to the pre-Slice-4 path.

        Two recomposition modes layer on top of the chain, both opt-in:

        **Shadow (P1.2)** — ``recomposition_plan is None``. When
        ``recomposition_sink`` is supplied, a SHADOW
        :class:`RecompositionReceipt` derived from the resulting ChainResult is
        handed to the sink AFTER the chain returns — advisory only,
        blocks/gates/retries nothing. The default (both ``None``) leaves the
        chain byte-identical: no receipt built, no sink called.

        **Enforcing (P3.2)** — ``recomposition_plan`` supplied (the admitted
        decomposition boundaries declared upstream). After the chain returns, an
        EFFECTIVE receipt accounts that plan against the chain's own traversal
        (:func:`enforce_recomposition`). If the chain did NOT itself refuse and
        the recomposition verdict is ``refused_laundering`` (a declared boundary
        the chain never accounted — a silently dropped slice), ``run`` returns a
        :class:`RecompositionRefusal` ChainResult (``seam == SEAM_RECOMPOSITION``)
        instead of the would-be-admissible outcome: the train stops, the laundered
        cargo is NOT forwarded, and downstream (keyed on ``ChainResult.refused``)
        does not proceed. Otherwise the chain result is returned unchanged —
        admissible and honestly-refused paths are byte-identical.

        Recomposition may stop the train; it may not choose the destination. The
        gate's ONLY effect is to convert a launderable success into a refusal: no
        client call, no mutation, no retry, no alternative outcome. The block
        decision is taken from the receipt's verdict, NOT from the sink — a
        misbehaving sink is swallowed (advisory emission is fail-open) but cannot
        suppress an enforcement refusal (the gate is fail-closed on laundering).
        Enforcement runs strictly AFTER ``_run_chain`` has fully returned, so it
        cannot change which client calls were made; it can only refuse to bless
        their recomposition.
        """
        result = self._run_chain(
            cooked_context,
            capacity_request_template,
            consume_request_template,
            now,
            finding_id=finding_id,
            standing_window=standing_window,
            playbook_evidence=playbook_evidence,
        )

        if recomposition_plan is None:
            # Shadow path (P1.2) — unchanged. Advisory emission only.
            if recomposition_sink is not None:
                self._emit_recomposition(
                    recomposition_sink,
                    shadow_recomposition(result, origin_mode=self._origin_mode),
                )
            return result

        # Enforcing path (P3.2). Decide the block AND build the refusal payload
        # from the SAME pre-emission snapshot, then emit. The refusal must be
        # decided before emission and reported from the same pre-emission
        # snapshot: by the time the advisory sink runs, both the block decision
        # (a local bool) and the returned diagnosis (a RecompositionRefusal whose
        # `accounting` was already computed) are fixed. So the sink can neither
        # suppress the block nor corrupt the reported diagnosis — both are
        # control-flow-independent of it, not merely protected by the receipt's
        # frozen-ness. (A determined in-process caller can still object.__setattr__
        # the shared receipt object's own fields; that is the same bootstrap-
        # custody substrate limit as P3.1 — admitted effect/control surface is
        # fenced, in-process object forgery is not, and the diagnosis we RETURN no
        # longer reads from that object after the sink touches it.)
        receipt = enforce_recomposition(
            result,
            origin_mode=self._origin_mode,
            recomposition_plan=recomposition_plan,
        )
        refusal: Optional[RecompositionRefusal] = None
        if (
            not result.refused
            and receipt.verdict == VERDICT_REFUSED_LAUNDERING
        ):
            refusal = RecompositionRefusal(
                receipt=receipt, accounting=receipt.accounting()
            )
        if recomposition_sink is not None:
            self._emit_recomposition(recomposition_sink, receipt)
        if refusal is not None:
            return ChainResult(outcome=refusal, seam=SEAM_RECOMPOSITION)
        return result

    @staticmethod
    def _emit_recomposition(
        sink: RecompositionSink, receipt: RecompositionReceipt
    ) -> None:
        """Hand a receipt to the sink, fail-open. Emission is advisory in BOTH
        modes: a raising sink must never raise through, gate, or alter the chain
        — and in enforcing mode it must not suppress the block either (the block
        is decided from the verdict by the caller, after this returns). Liveness
        of an opt-in sink is the caller's, the same coupling run() already has to
        its synchronous receipt sink."""
        try:
            sink(receipt)
        except Exception:
            pass

    def _run_chain(
        self,
        cooked_context: CookedContext,
        capacity_request_template: CookedCapacityRequest,
        consume_request_template: CookedConsumeRequest,
        now: int,
        *,
        finding_id: Optional[str] = None,
        standing_window: Optional[StandingWindow] = None,
        playbook_evidence: Optional[PlaybookAdmissionEvidence] = None,
    ) -> ChainResult:
        """Drive standing → wicket → [standing-spendability] → LA-request → LA-consume.

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
        #
        # Slice 4: when playbook evidence is supplied, route through the
        # two-gate playbook admission (evidence coherence → authority).
        # Both paths return the same WicketRefusal | WicketVerdict union, so
        # a playbook_evidence_unbound refusal lands at SEAM_WICKET exactly
        # like a standing refusal, and a verdict threads its pass-admission
        # receipt id downstream exactly the same. The evidence record is a
        # side receipt (verdict=observe); it is never on the WicketVerdict, so
        # it cannot become the spend basis through this path.
        if playbook_evidence is not None:
            wicket_result = self._wicket.check_playbook_admission(
                cooked_context, playbook_evidence, finding_id=finding_id
            )
        else:
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

        # Step 1.5 (optional): standing-before-spendability gate. The standing
        # was admissible (wicket said yes), but is it still FRESH enough to
        # spend on at exercise time? A standing observed at T1 with a horizon
        # expiring before the exercise has lapsed in the gap — admitted yet
        # void. The gate refuses BEFORE any capacity is reserved or spent
        # (the lapse must not cost budget). Only runs when a gate is composed
        # AND a window is supplied; otherwise the chain is unchanged.
        if self._spendability_gate is not None and standing_window is not None:
            # Lineage at emission: the gate's receipt cites the admission
            # (wicket) receipt as parent, so the refusal chain walks
            # refusal → wicket → standing → finding, same as the consume path.
            spend_check = self._spendability_gate.check(
                standing_window, parent_receipt_ids=(admission_receipt_id,)
            )
            if isinstance(spend_check, SpendabilityRefusal):
                return ChainResult(
                    outcome=spend_check, seam=SEAM_STANDING_SPENDABILITY
                )

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
