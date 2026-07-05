# SPDX-License-Identifier: Apache-2.0
"""WorkContainer ⇄ gate-receipt bridge — Slice 4b of the provider integration contract.

DRAFT / CANDIDATE substrate. The live emission/consumption seam that S4 named as its
gated follow-on. S4a proved a WorkContainer can *describe* the proven live path;
S4b makes admission a first-class, resolvable AG `GateReceipt` and makes consumption
*re-verify* the container against it.

Two moves, and the boundary that keeps them honest:

- **Emit** (:func:`emit_admission_receipt`, :func:`admit_cd4b`) — mint a real
  ``work_admission`` :class:`~governor.gate_receipt.GateReceipt` (verdict ``proceed``,
  role ``measurement``) over the *verified* admission basis (plan_ref + citations +
  scope/ration source refs), and bind the container's ``admission_ref`` to that
  receipt (``sha256:<receipt_id>``). This replaces S4a's bootstrap basis-seal with a
  stored decision a consumer can look up. Fail-closed: no receipt is minted for an
  unverified basis. The receipt is a **measurement** — it *records* that the basis
  verified and the work may proceed; it does NOT mint a role=``authority`` grant
  (that stays the operator's act via ``plan_review.authorize_agenda`` — a gated,
  operator-in-the-loop path, named not built here). The operator approval witness is
  bound as evidence, so the force still traces to the operator, not to this bridge.

- **Consume** (:func:`resolve_admission`, :func:`dispatch_preflight`) — resolve
  ``admission_ref`` to a real receipt AND check the receipt's evidence *binds the same
  basis* the container carries. A well-formed, well-sealed container that cites an
  admission which does not exist (or which admitted *different* work) is refused. This
  is the NLAI point made mechanical: possession/validity is not admission — reliance
  requires re-verifying ``admission_ref``, and ``verify_container`` alone is not enough.

What S4b deliberately does NOT do (the boundaries S4 preserved):

- **No live agent launch.** ``dispatch_preflight`` returns a decision; actually
  running an agent stays the runtime supervisor's job. The live-run surface is not
  broadened.
- **The registry does not decide.** ``allow`` depends ONLY on container verification
  + admission resolution. A missing/absent provider descriptor is a *routing* gap
  (admitted-but-unroutable), never an admission refusal — registry presence/absence
  cannot change the verdict (the S4 invariant, held at the dispatch layer too).
- **Provider testimony is not admission.** Nothing a provider reports feeds back
  into ``allow``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Optional

from governor.gate_receipt import (
    ROLE_MEASUREMENT,
    GateReceipt,
    GateReceiptSystem,
    canonical_json,
)

from governor.work_container import (
    Citation,
    WorkContainer,
    WorkContainerError,
    _is_sha256_ref,
    project_cd4b_work_container,
    verify_container,
)

WORK_ADMISSION_GATE = "work_admission"
WORK_ADMISSION_VERDICT = "proceed"
#: The role this bridge mints an admission as — a recorded decision, not a grant.
WORK_ADMISSION_ROLE = ROLE_MEASUREMENT
_SHA256_PREFIX = "sha256:"

#: The only verdict that admits work here — exactly what emit mints. Fail-closed:
#: accepting a wider set would trust receipts this bridge never produces.
_ADMITTING_VERDICTS = frozenset({WORK_ADMISSION_VERDICT})


# --------------------------------------------------------------------------- #
# Refusal vocabulary (fail-closed; distinct from projection-time errors).
# --------------------------------------------------------------------------- #


class AdmissionError(WorkContainerError):
    """Base for consume-side admission refusals."""


class AdmissionNotFoundError(AdmissionError):
    """``admission_ref`` does not resolve to a stored receipt — the container cites
    an admission that does not exist."""


class AdmissionBindingError(AdmissionError):
    """The resolved receipt admitted *different* work than the container carries —
    its evidence does not bind the container's basis."""


class AdmissionRefusedError(AdmissionError):
    """The resolved receipt did not admit the work (verdict is not proceed/pass)."""


# --------------------------------------------------------------------------- #
# Admission evidence — the exact bytes the receipt binds and consume re-checks.
# --------------------------------------------------------------------------- #


def build_admission_evidence(
    *,
    plan_ref: str,
    citations: tuple[Citation, ...],
    scope_source_ref: str,
    ration_source_ref: str,
) -> dict[str, Any]:
    """The admission-basis evidence bundle. Deterministic (canonical_json seals it in
    the receipt). Consume re-derives this shape from the container and compares."""
    return {
        "record_kind": "work_admission",
        "plan_ref": plan_ref,
        "citations": [c.as_dict() for c in citations],
        "scope_source_ref": scope_source_ref,
        "ration_source_ref": ration_source_ref,
        "all_citations_verified": all(c.verified for c in citations),
    }


def emit_admission_receipt(
    receipts: GateReceiptSystem,
    *,
    plan_ref: str,
    citations: tuple[Citation, ...],
    scope_source_ref: str,
    ration_source_ref: str,
    principal_id: str = "local",
) -> GateReceipt:
    """Mint a first-class ``work_admission`` receipt over the verified basis.

    Fail-closed: refuses to mint for an empty or unverified citation set — an
    admission receipt is only produced for admitted work. Role ``measurement`` /
    verdict ``proceed``: it records the admission decision, it does not mint an
    authority grant (see module docstring).
    """
    if not citations:
        raise WorkContainerError("cannot admit work with no citations")
    if not all(c.verified for c in citations):
        unverified = [c.name for c in citations if not c.verified]
        raise WorkContainerError(
            f"refusing to mint admission for unverified citations {unverified}"
        )
    # The basis refs must be well-formed content-addresses — a proceed receipt is
    # not minted over a malformed basis (fail-closed on the whole basis, not just
    # the citation booleans).
    for label, ref in (
        ("plan_ref", plan_ref),
        ("scope_source_ref", scope_source_ref),
        ("ration_source_ref", ration_source_ref),
    ):
        if not _is_sha256_ref(ref):
            raise WorkContainerError(
                f"refusing to mint admission: {label} {ref!r} is not a sha256 citation"
            )
    evidence = build_admission_evidence(
        plan_ref=plan_ref,
        citations=citations,
        scope_source_ref=scope_source_ref,
        ration_source_ref=ration_source_ref,
    )
    return receipts.emit(
        gate=WORK_ADMISSION_GATE,
        verdict=WORK_ADMISSION_VERDICT,
        subject_kind="work_admission",
        subject_bytes=canonical_json({"plan_ref": plan_ref}),
        evidence_bundle=evidence,
        gate_config={"seam": "S4b", "contract": "work_container.v1"},
        principal_id=principal_id,
        receipt_role=ROLE_MEASUREMENT,
    )


def admission_ref_for(receipt: GateReceipt) -> str:
    """The ``admission_ref`` citation for a receipt: ``sha256:<receipt_id>``."""
    return _SHA256_PREFIX + receipt.receipt_id


# --------------------------------------------------------------------------- #
# Consume — resolve + bind-check (the NLAI re-verification made mechanical).
# --------------------------------------------------------------------------- #


def resolve_admission(
    container_dict: dict[str, Any], receipts: GateReceiptSystem
) -> GateReceipt:
    """Resolve a container's ``admission_ref`` to a real receipt and refuse unless it
    genuinely admitted THIS work.

    Steps (each a fail-closed gate):
    1. ``admission_ref`` must resolve to a stored receipt (:class:`AdmissionNotFoundError`).
    2. the receipt must be a ``work_admission`` receipt with this bridge's role
       (``measurement``) and admitting verdict (``proceed``) — a receipt of the wrong
       gate/verdict/role is refused (:class:`AdmissionBindingError` /
       :class:`AdmissionRefusedError`).
    3. the receipt's evidence must BIND the container's WHOLE basis — same plan_ref,
       same citation set, same scope AND ration source refs, and honest admission
       metadata (:class:`AdmissionBindingError`). This is the load-bearing check: a
       forged container cannot borrow a receipt admitting different (e.g. broader-
       scoped) work.
    """
    admission_ref = container_dict.get("admission_ref", "")
    if not isinstance(admission_ref, str) or not admission_ref.startswith(_SHA256_PREFIX):
        raise AdmissionNotFoundError(f"malformed admission_ref {admission_ref!r}")
    receipt_id = admission_ref[len(_SHA256_PREFIX) :]

    receipt = receipts.receipt_store.get_by_id(receipt_id)
    if receipt is None:
        raise AdmissionNotFoundError(
            f"admission_ref {admission_ref} resolves to no stored receipt"
        )
    if receipt.gate != WORK_ADMISSION_GATE:
        raise AdmissionBindingError(
            f"receipt {receipt_id} is a {receipt.gate!r} receipt, not a work_admission"
        )
    if receipt.receipt_role != WORK_ADMISSION_ROLE:
        raise AdmissionBindingError(
            f"admission receipt role {receipt.receipt_role!r} != {WORK_ADMISSION_ROLE!r}"
        )
    if receipt.verdict not in _ADMITTING_VERDICTS:
        raise AdmissionRefusedError(
            f"admission receipt verdict {receipt.verdict!r} did not admit the work"
        )

    evidence = receipts.evidence_store.get(receipt.evidence_hash)
    if evidence is None:
        raise AdmissionBindingError(
            f"admission receipt {receipt_id} has no retrievable evidence"
        )

    # The receipt's evidence must be an honest, complete work-admission basis…
    if evidence.get("record_kind") != "work_admission":
        raise AdmissionBindingError("admission evidence is not a work_admission record")
    if evidence.get("all_citations_verified") is not True:
        raise AdmissionBindingError("admission evidence does not attest all citations verified")

    # …and it must bind THIS container's whole basis (every source, not just plan).
    basis = container_dict.get("admission_basis") or {}
    origin = container_dict.get("origin") or {}
    scope = container_dict.get("scope_projection") or {}
    ration = container_dict.get("ration_projection") or {}
    binds = (
        ("plan_ref", evidence.get("plan_ref"), origin.get("proposal_ref")),
        ("citations", evidence.get("citations"), basis.get("citations", [])),
        ("scope_source_ref", evidence.get("scope_source_ref"), scope.get("source_ref")),
        ("ration_source_ref", evidence.get("ration_source_ref"), ration.get("source_ref")),
    )
    for name, from_receipt, from_container in binds:
        if from_receipt != from_container:
            raise AdmissionBindingError(
                f"admission receipt {name} does not match the container's basis"
            )
    return receipt


@dataclasses.dataclass(frozen=True)
class DispatchVerdict:
    """The bailiff's decision. ``allow`` rests on container verification + admission
    resolution ONLY. ``provider`` / ``provider_known`` are routing information: a
    missing descriptor is an *admitted-but-unroutable* gap, never an admission
    refusal (registry presence/absence cannot change ``allow``)."""

    allow: bool
    admission_receipt_id: Optional[str]
    provider: Optional[str]
    provider_known: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "admission_receipt_id": self.admission_receipt_id,
            "provider": self.provider,
            "provider_known": self.provider_known,
            "reasons": list(self.reasons),
        }


def dispatch_preflight(
    container_dict: dict[str, Any],
    receipts: GateReceiptSystem,
    registry: Any | None = None,
) -> DispatchVerdict:
    """Decide whether an admitted WorkContainer may be routed for dispatch.

    Fail-closed: any verification/admission failure yields ``allow=False`` with a
    reason (a refusal is a normal decision, like ``governed_dispatch``'s ``blocked``).
    Does NOT launch anything. The registry, if given, supplies routing candidates
    only — it never flips ``allow``.
    """
    reasons: list[str] = []

    # Gate 1: the container must be structurally sound + internally honest.
    try:
        verify_container(container_dict)
    except WorkContainerError as exc:
        return DispatchVerdict(False, None, None, False, (f"container_invalid: {exc}",))

    # Gate 2: admission must resolve to a real receipt that admitted THIS work.
    try:
        receipt = resolve_admission(container_dict, receipts)
    except AdmissionError as exc:
        return DispatchVerdict(False, None, None, False, (f"admission_unresolved: {exc}",))

    # Routing info only — NEVER a gate on allow (registry independence).
    provider = ((container_dict.get("routing") or {}).get("eligible_provider"))
    provider_known = False
    if registry is not None and provider:
        # A failing registry is a routing gap, NEVER an admission outcome: swallow it
        # so registry state can neither flip allow nor abort an already-admitted
        # decision (registry-independence held even against a broken registry).
        try:
            entry = registry.get(provider)
        except Exception as exc:  # noqa: BLE001 - registry faults must not gate admission
            entry = None
            reasons.append(f"registry lookup failed ({exc}); provider routing unknown")
        provider_known = entry is not None and not getattr(entry, "revoked", False)
        if entry is None and not reasons:
            reasons.append(
                f"provider {provider!r} not a live registry candidate (admitted but unrouted)"
            )

    return DispatchVerdict(
        allow=True,
        admission_receipt_id=receipt.receipt_id,
        provider=provider,
        provider_known=provider_known,
        reasons=tuple(reasons),
    )


# --------------------------------------------------------------------------- #
# CD-4B demonstration — the receipt-backed container over the proven shape.
# --------------------------------------------------------------------------- #


def admit_cd4b(
    receipts: GateReceiptSystem, specimen_dir: str | Path
) -> tuple[GateReceipt, WorkContainer]:
    """Emit a real admission receipt for the CD-4B specimen and return a
    receipt-backed container (``admission_ref`` = the stored receipt), alongside the
    receipt. The S4a projection's fields are reused verbatim; only ``admission_ref``
    changes — from the bootstrap basis-seal to a resolvable receipt id."""
    wc = project_cd4b_work_container(specimen_dir)
    receipt = emit_admission_receipt(
        receipts,
        plan_ref=wc.origin.proposal_ref,
        citations=wc.admission_basis.citations,
        scope_source_ref=wc.scope_projection.source_ref,
        ration_source_ref=wc.ration_projection.source_ref,
        principal_id="operator",
    )
    backed = dataclasses.replace(wc, admission_ref=admission_ref_for(receipt))
    return receipt, backed


__all__ = [
    "WORK_ADMISSION_GATE",
    "WORK_ADMISSION_VERDICT",
    "WORK_ADMISSION_ROLE",
    "AdmissionError",
    "AdmissionNotFoundError",
    "AdmissionBindingError",
    "AdmissionRefusedError",
    "build_admission_evidence",
    "emit_admission_receipt",
    "admission_ref_for",
    "resolve_admission",
    "DispatchVerdict",
    "dispatch_preflight",
    "admit_cd4b",
]
