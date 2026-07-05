# SPDX-License-Identifier: Apache-2.0
"""WorkContainer projection — Slice 4 of the provider/agent integration contract.

DRAFT / CANDIDATE substrate. **Projection, not delegation.**

A :class:`WorkContainer` is the serialized wire record that carries *already-admitted*
work across a provider boundary (see ``docs/api/work-container-contract.md`` +
``schemas/work_container.v1.json``). This module builds one by **projecting existing,
shipped Agent Governor artifacts** — it invents no law-bearing field, mints no
authority, and grants no permission. Every scope/ration/admission/custody value
traces back to a shipped object (RationCard / QueuedPlaybook / governed-plan
governance block / gate-receipt discipline); the projector is a pure function over
those inputs.

What this module is NOT (the boundaries that make it safe):

- **Not admission.** A produced container carries ``admission_ref`` — a citation to
  the AG admission decision that must be RE-VERIFIED, never trusted. Schema validity
  and a good custody seal are never sufficient to invoke or rely.
- **Not a grant.** ``scope_projection`` / ``ration_projection`` are read-only
  snapshots of a RationCard (each carries the ``source_ref`` it projects). A provider
  may only *further restrict* them; ``governed_dispatch`` remains the enforcement
  source.
- **Not dispatch.** This module has no run / dispatch / execute verb. It returns
  data. Provider selection and dispatch stay in ``governed_dispatch``; provider
  eligibility is a phone-book lookup in ``provider_registry`` (which this module
  never consults — registry presence/absence cannot change a projection).
- **Not a trust signal about a provider.** ``routing.eligible_provider`` is a LABEL
  (a candidate a dispatcher MAY select), and ``produced_receipts`` is provider
  TESTIMONY — a provider's success/status can never be read as admitted success.

Fail-closed: a projection is refused (raises) if any load-bearing citation is
unverified, if ``admission_ref`` is malformed, or if a seal does not recompute.

Evidence spine: the CD-4B live drive (session ``sess_aabb2a056f9f``,
``docs/campaigns/conveyor-dogfood/specimens/cd4-docs-normalize/CD4B_DRIVE.md``).
``project_cd4b_work_container`` projects that proven runtime shape.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from governor.gate_receipt import canonical_json, content_hash

WORK_CONTAINER_SCHEMA_VERSION = "work_container.v1"

#: The capability vocabulary is reused verbatim from chain_gate — not a new enum.
try:  # keep the import local-tolerant; validation below does not require it present
    from governor.chain_gate import CapabilityClass

    _CAPABILITY_VALUES = frozenset(c.value for c in CapabilityClass)
except Exception:  # pragma: no cover - chain_gate is always present in-repo
    _CAPABILITY_VALUES = frozenset(
        {
            "file_read",
            "file_write",
            "network_egress",
            "network_ingress",
            "shell_exec",
            "code_exec",
            "model_call",
            "unknown",
        }
    )


# --------------------------------------------------------------------------- #
# Fail-closed refusal vocabulary.
# --------------------------------------------------------------------------- #


class WorkContainerError(ValueError):
    """Base for every projection refusal. A projection never degrades to a
    best-effort container; it raises."""


class UnverifiedCitationError(WorkContainerError):
    """A load-bearing citation was not verified. An admitted governed plan whose
    citations do not all resolve is not admitted work — refuse to project it."""


class MalformedAdmissionRefError(WorkContainerError):
    """``admission_ref`` is not a ``sha256:<64hex>`` citation."""


class DigestMismatchError(WorkContainerError):
    """A recomputed seal / admission basis does not match the stored digest —
    the projection is stale or tampered. Fail closed."""


_SHA256_PREFIX = "sha256:"


def _is_sha256_ref(ref: Any) -> bool:
    if not isinstance(ref, str) or not ref.startswith(_SHA256_PREFIX):
        return False
    hexpart = ref[len(_SHA256_PREFIX) :]
    return len(hexpart) == 64 and all(c in "0123456789abcdef" for c in hexpart)


def sha256_ref_of_bytes(data: bytes) -> str:
    """``sha256:<hex>`` over raw bytes — the content-address discipline the CD-4B
    admission used for every citation (raw file bytes), reused here verbatim."""
    return _SHA256_PREFIX + hashlib.sha256(data).hexdigest()


def _seal_over(body: dict[str, Any]) -> str:
    """Canonical-JSON + sha256 seal, reusing gate_receipt.canonical_json (do not
    re-derive canonicalization)."""
    return _SHA256_PREFIX + content_hash(canonical_json(body))


# --------------------------------------------------------------------------- #
# Structured projection blocks (each a read-only snapshot of a shipped object).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Citation:
    """One admission citation and whether admission independently resolved it.
    ``ref`` is a content-address (``sha256:<hex>``) or a witness path (approval_ref
    is a filename, not a digest) — free-form on purpose."""

    name: str
    ref: str
    verified: bool

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ref": self.ref, "verified": self.verified}


@dataclass(frozen=True)
class Origin:
    """Where the work came from. Labels + citations, never standing."""

    submitted_by: str  # actor label only, not standing
    proposal_ref: Optional[str] = None  # governed-plan digest (the admitted proposal)
    playbook_ref: Optional[str] = None  # PlaybookSpec/QueuedPlaybook digest
    standing_basis_ref: Optional[str] = None  # citation to a standing receipt, if any

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"submitted_by": self.submitted_by}
        if self.proposal_ref is not None:
            out["proposal_ref"] = self.proposal_ref
        if self.playbook_ref is not None:
            out["playbook_ref"] = self.playbook_ref
        if self.standing_basis_ref is not None:
            out["standing_basis_ref"] = self.standing_basis_ref
        return out


@dataclass(frozen=True)
class ScopeProjection:
    """Read-only snapshot of path scope. NOT a grant — a provider may only further
    restrict. ``source_ref`` is the RationCard digest the write scope projects from;
    read/forbidden paths may additionally project the QueuedPlaybook cited in
    ``admission_basis`` (both refs live in the container, both re-verifiable)."""

    source_ref: str
    allowed_read_paths: tuple[str, ...] = ()
    allowed_write_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "allowed_read_paths": list(self.allowed_read_paths),
            "allowed_write_paths": list(self.allowed_write_paths),
            "forbidden_paths": list(self.forbidden_paths),
        }


@dataclass(frozen=True)
class RationProjection:
    """Read-only snapshot of the RationCard locked axes. NOT a grant; a provider may
    only further restrict. ``external_send`` has no RationCard axis, so it projects
    fail-closed False (an observe-only, network-locked card cannot externally
    send)."""

    source_ref: str
    network: bool
    external_send: bool
    git: bool
    doctrine_writes: bool
    observe_only: bool
    max_wallclock_seconds: Optional[int] = None
    max_artifact_bytes: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "source_ref": self.source_ref,
            "network": self.network,
            "external_send": self.external_send,
            "git": self.git,
            "doctrine_writes": self.doctrine_writes,
            "observe_only": self.observe_only,
        }
        if self.max_wallclock_seconds is not None:
            out["max_wallclock_seconds"] = self.max_wallclock_seconds
        if self.max_artifact_bytes is not None:
            out["max_artifact_bytes"] = self.max_artifact_bytes
        return out


@dataclass(frozen=True)
class Acceptance:
    required_checks: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.required_checks and not self.required_artifacts

    def as_dict(self) -> dict[str, Any]:
        return {
            "required_checks": list(self.required_checks),
            "required_artifacts": list(self.required_artifacts),
        }


@dataclass(frozen=True)
class ReceiptExpectations:
    run_receipt: bool = True
    obstruction_on_block: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_receipt": self.run_receipt,
            "obstruction_on_block": self.obstruction_on_block,
        }


@dataclass(frozen=True)
class Routing:
    """Routing eligibility LABELS — never trust, never a grant. ``eligible_provider``
    names a provider a ``governed_dispatch`` MAY select; the registry is not consulted
    to build this and its presence/absence cannot change the container."""

    eligible_provider: Optional[str] = None
    forbidden_providers: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return self.eligible_provider is None and not self.forbidden_providers

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.eligible_provider is not None:
            out["eligible_provider"] = self.eligible_provider
        if self.forbidden_providers:
            out["forbidden_providers"] = list(self.forbidden_providers)
        return out


@dataclass(frozen=True)
class ProducedReceipts:
    """PRODUCED provider testimony for this container — a ReviewPacket reference /
    obstruction / run identity. TESTIMONY, never admission: a provider's
    success/status here can NEVER be read as admitted success (contract §4.1).
    Reliance still requires re-verifying ``admission_ref`` and re-running the
    ReviewPacket validator."""

    review_packet_ref: Optional[str] = None
    review_packet_status: Optional[str] = None
    obstruction_ref: Optional[str] = None
    run_session_id: Optional[str] = None
    promotion_id: Optional[str] = None

    def is_empty(self) -> bool:
        return all(
            v is None
            for v in (
                self.review_packet_ref,
                self.review_packet_status,
                self.obstruction_ref,
                self.run_session_id,
                self.promotion_id,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in (
            "review_packet_ref",
            "review_packet_status",
            "obstruction_ref",
            "run_session_id",
            "promotion_id",
        ):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out


@dataclass(frozen=True)
class AdmissionBasis:
    """The citation set admission verified — a re-verifiable RECORD, not a grant.
    ``all_citations_verified`` is the conjunction over ``citations``; a container is
    only produced when it is True (false is unrepresentable — the projector
    refuses)."""

    citations: tuple[Citation, ...]

    @property
    def all_citations_verified(self) -> bool:
        return all(c.verified for c in self.citations)

    def as_dict(self) -> dict[str, Any]:
        return {
            "citations": [c.as_dict() for c in self.citations],
            "all_citations_verified": self.all_citations_verified,
        }


@dataclass(frozen=True)
class Custody:
    """Custody lineage. ``digest`` (the seal) is derived, never stored on the
    dataclass — it is computed over the canonical body sans the digest field, so it
    cannot silently disagree with the content."""

    parent_container_ref: Optional[str] = None
    decomposition_lineage: tuple[str, ...] = ()

    def as_dict_without_seal(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.parent_container_ref is not None:
            out["parent_container_ref"] = self.parent_container_ref
        if self.decomposition_lineage:
            out["decomposition_lineage"] = list(self.decomposition_lineage)
        return out


# --------------------------------------------------------------------------- #
# The container.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkContainer:
    """A sealed, serialized projection of already-admitted work. Evidence + a bill of
    lading, not a second Governor. Its custody ``digest`` is computed on
    serialization; ``admission_ref`` is a citation to re-verify."""

    work_id: str
    admission_ref: str
    origin: Origin
    intent: str
    scope_projection: ScopeProjection
    ration_projection: RationProjection
    custody: Custody
    capability_requirements: tuple[str, ...] = ()
    admission_basis: Optional[AdmissionBasis] = None
    acceptance: Optional[Acceptance] = None
    stop_conditions: tuple[str, ...] = ()
    receipt_expectations: Optional[ReceiptExpectations] = None
    routing: Optional[Routing] = None
    produced_receipts: Optional[ProducedReceipts] = None

    # -- serialization ------------------------------------------------------- #

    def _body_without_seal(self) -> dict[str, Any]:
        """The canonical body used to compute the custody seal — every field except
        ``custody.digest`` itself."""
        body: dict[str, Any] = {
            "schema_version": WORK_CONTAINER_SCHEMA_VERSION,
            "work_id": self.work_id,
            "admission_ref": self.admission_ref,
            "origin": self.origin.as_dict(),
            "intent": self.intent,
            "scope_projection": self.scope_projection.as_dict(),
            "ration_projection": self.ration_projection.as_dict(),
            "custody": self.custody.as_dict_without_seal(),
        }
        if self.capability_requirements:
            body["capability_requirements"] = list(self.capability_requirements)
        if self.admission_basis is not None:
            body["admission_basis"] = self.admission_basis.as_dict()
        if self.acceptance is not None and not self.acceptance.is_empty():
            body["acceptance"] = self.acceptance.as_dict()
        if self.stop_conditions:
            body["stop_conditions"] = list(self.stop_conditions)
        if self.receipt_expectations is not None:
            body["receipt_expectations"] = self.receipt_expectations.as_dict()
        if self.routing is not None and not self.routing.is_empty():
            body["routing"] = self.routing.as_dict()
        if self.produced_receipts is not None and not self.produced_receipts.is_empty():
            body["produced_receipts"] = self.produced_receipts.as_dict()
        return body

    def seal(self) -> str:
        """The custody digest: ``sha256:<hex>`` over the canonical body sans seal."""
        return _seal_over(self._body_without_seal())

    def to_schema_dict(self) -> dict[str, Any]:
        """The full work_container.v1 wire shape, with the custody seal applied."""
        body = self._body_without_seal()
        custody = dict(body["custody"])
        custody["digest"] = self.seal()
        body["custody"] = custody
        return body

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_schema_dict(), sort_keys=True, indent=2)


def verify_seal(schema_dict: dict[str, Any]) -> None:
    """Recompute the custody seal from a wire ``schema_dict`` and refuse on mismatch.
    Fail-closed: a stale or tampered container does not validate."""
    stored = (schema_dict.get("custody") or {}).get("digest")
    if not _is_sha256_ref(stored):
        raise DigestMismatchError("custody.digest missing or malformed")
    body = {k: v for k, v in schema_dict.items() if k != "custody"}
    custody = {k: v for k, v in (schema_dict.get("custody") or {}).items() if k != "digest"}
    body["custody"] = custody
    recomputed = _seal_over(body)
    if recomputed != stored:
        raise DigestMismatchError(
            f"custody.digest {stored} does not match recomputed {recomputed}"
        )


def verify_container(schema_dict: dict[str, Any]) -> None:
    """Read-side gate over a wire container. Refuses (raises) a container that is
    tampered, malformed, or internally lying — the seal alone is integrity, not
    authority (a content hash, not a signature: a forger can recompute it), so this
    also enforces the non-laundering invariants a consumer would otherwise trust:

    - the custody seal recomputes (:func:`verify_seal`);
    - ``admission_ref`` is a ``sha256:<64hex>`` citation;
    - ``admission_basis.all_citations_verified`` is not a lie — it must equal the
      conjunction over ``citations[].verified`` AND be true (an unverified basis is
      not admitted work).

    This is NOT admission, and it is NOT full schema validation (run a JSON-Schema
    validator against ``schemas/work_container.v1.json`` separately — this gate does
    not enumerate every field). A passing container is still only *evidence to
    re-verify*: reliance requires re-checking ``admission_ref`` against the real
    witnesses and re-running the ReviewPacket validator.
    """
    if schema_dict.get("schema_version") != WORK_CONTAINER_SCHEMA_VERSION:
        raise WorkContainerError(
            f"schema_version {schema_dict.get('schema_version')!r} != "
            f"{WORK_CONTAINER_SCHEMA_VERSION!r}"
        )
    verify_seal(schema_dict)
    if not _is_sha256_ref(schema_dict.get("admission_ref")):
        raise MalformedAdmissionRefError("admission_ref missing or malformed")
    basis = schema_dict.get("admission_basis")
    if basis is not None:
        citations = basis.get("citations") or []
        conjunction = bool(citations) and all(bool(c.get("verified")) for c in citations)
        if bool(basis.get("all_citations_verified")) != conjunction:
            raise UnverifiedCitationError(
                "all_citations_verified disagrees with citations[].verified (forged basis)"
            )
        if not conjunction:
            raise UnverifiedCitationError(
                "admission_basis has unverified citations — not admitted work"
            )


# --------------------------------------------------------------------------- #
# The projection primitive — pure over shipped inputs. No registry. No dispatch.
# --------------------------------------------------------------------------- #


def project_work_container(
    *,
    work_id: str,
    admission_ref: str,
    origin: Origin,
    intent: str,
    scope_projection: ScopeProjection,
    ration_projection: RationProjection,
    admission_basis: AdmissionBasis,
    capability_requirements: tuple[str, ...] = (),
    acceptance: Optional[Acceptance] = None,
    stop_conditions: tuple[str, ...] = (),
    receipt_expectations: Optional[ReceiptExpectations] = None,
    routing: Optional[Routing] = None,
    produced_receipts: Optional[ProducedReceipts] = None,
    custody: Optional[Custody] = None,
) -> WorkContainer:
    """Project a :class:`WorkContainer` from already-shipped AG inputs.

    Pure and total-or-refuse: it consults no registry, performs no dispatch, does no
    IO. It fails closed when the inputs describe work that is not admitted:

    - ``admission_ref`` must be a ``sha256:<64hex>`` citation (raises
      :class:`MalformedAdmissionRefError`).
    - every citation in ``admission_basis`` must be verified (raises
      :class:`UnverifiedCitationError`) — an admitted governed plan whose citations
      do not all resolve is not admitted work.
    - unknown capability requirements are refused (kept inside the chain_gate vocab).
    """
    if not _is_sha256_ref(admission_ref):
        raise MalformedAdmissionRefError(
            f"admission_ref {admission_ref!r} is not a sha256:<64hex> citation"
        )
    if not admission_basis.citations:
        raise UnverifiedCitationError("admission_basis carries no citations")
    if not admission_basis.all_citations_verified:
        unverified = [c.name for c in admission_basis.citations if not c.verified]
        raise UnverifiedCitationError(
            f"unverified citations {unverified} — refusing to project unadmitted work"
        )
    bad_caps = sorted(set(capability_requirements) - _CAPABILITY_VALUES)
    if bad_caps:
        raise WorkContainerError(
            f"unknown capability_requirements {bad_caps} (not in chain_gate.CapabilityClass)"
        )
    # Every projection must cite the source it snapshots by content-address, so the
    # snapshot is re-verifiable against that source (they may differ — scope may cite
    # a QueuedPlaybook while ration cites a RationCard — so equality is NOT required).
    for label, ref in (
        ("scope_projection", scope_projection.source_ref),
        ("ration_projection", ration_projection.source_ref),
    ):
        if not _is_sha256_ref(ref):
            raise WorkContainerError(
                f"{label}.source_ref {ref!r} is not a sha256:<64hex> citation"
            )
    return WorkContainer(
        work_id=work_id,
        admission_ref=admission_ref,
        origin=origin,
        intent=intent,
        scope_projection=scope_projection,
        ration_projection=ration_projection,
        custody=custody if custody is not None else Custody(),
        capability_requirements=tuple(capability_requirements),
        admission_basis=admission_basis,
        acceptance=acceptance,
        stop_conditions=tuple(stop_conditions),
        receipt_expectations=receipt_expectations,
        routing=routing,
        produced_receipts=produced_receipts,
    )


# --------------------------------------------------------------------------- #
# CD-4B specimen projector — the proven live shape, projected.
# --------------------------------------------------------------------------- #

CD4B_SESSION_ID = "sess_aabb2a056f9f"
CD4B_PROMOTION_ID = "prom_33a118903e71"

# Files the CD-4B flip dirtied — the operator's own approval acts — which the
# Tock-2 baseline fence EXCLUDES from the run's promote/discard. They are the
# admission citations, not the run's output; the projection records them as such.
CD4B_FENCED_FLIP_FILES = (
    "plan.md",
    "queue.json",
    "operator_queued_playbook.operator_approved_2026-07-04",
)


def _load_plan_front_matter(plan_md: Path) -> dict[str, Any]:
    """Extract the YAML front matter from the governed plan (between the first two
    ``---`` fences)."""
    import yaml

    text = plan_md.read_text()
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise WorkContainerError(f"{plan_md} has no YAML front matter")
    return yaml.safe_load(parts[1]) or {}


def project_cd4b_work_container(specimen_dir: str | Path) -> WorkContainer:
    """Project the CD-4B live-run shape into a WorkContainer.

    Reads the specimen artifacts (the governed ``plan.md``, ``ration_card.json``,
    ``queue.json``, ``playbook.yaml``, and the produced ``review_packet.manifest.json``)
    and projects them faithfully. Every citation ref is the RAW-BYTES sha256 of its
    witness file — exactly the content-address CD-4B admission verified — so the
    projection is re-verifiable against the tree, not a hand-copied assertion.

    ``admission_ref`` is the re-verifiable seal over the admission basis (plan_ref +
    the verified citation set). CD-4B admission lived in the maude M-2 parser plus the
    operator's witness file rather than a first-class AG ``GateReceipt``; emitting that
    receipt from ``governed_dispatch`` is the gated live-wiring follow-on (contract §8,
    Slice 4). Until then this basis digest is the honest, recomputable admission
    citation — and the container is still only *evidence to re-verify*, never
    admission.
    """
    import json

    d = Path(specimen_dir)

    plan_bytes = (d / "plan.md").read_bytes()
    ration_bytes = (d / "ration_card.json").read_bytes()
    queue_bytes = (d / "queue.json").read_bytes()
    playbook_bytes = (d / "playbook.yaml").read_bytes()

    plan_ref = sha256_ref_of_bytes(plan_bytes)
    ration_card_ref = sha256_ref_of_bytes(ration_bytes)
    queued_playbook_ref = sha256_ref_of_bytes(queue_bytes)
    playbook_digest = sha256_ref_of_bytes(playbook_bytes)

    fm = _load_plan_front_matter(d / "plan.md")
    gov = fm.get("governance", {}) or {}
    intent = fm.get("goal", "")
    approval_ref = gov.get("approval_ref", "")

    # Cross-check the front-matter's declared digests against the witness files. A
    # mismatch means the plan cites something other than what is on disk — the
    # citation is NOT verified, and the projector will refuse it below.
    def _cited(name: str) -> str:
        return gov.get(name, "")

    # approval_ref is a witness *filename* (not a digest). Content-witnessing the
    # approval — "a written 'approved' is prose until independently witnessed" — is
    # maude M-1's job at admission (refusal: governance_approval_unverified, CD-1a).
    # AG-side the projector cannot re-run that logic, so it must NOT overclaim: this
    # citation is "verified" only when the plan itself DECLARES approval AND its named
    # witness is actually present and non-empty. Bare file existence is not enough
    # (an empty stub would spoof it); the strong re-verification is the three digest
    # citations below, whose refs are raw-bytes hashes that must match the tree.
    witness = d / approval_ref if approval_ref else None
    approval_verified = (
        gov.get("governance_status") == "approved"
        and bool(approval_ref)
        and witness is not None
        and witness.exists()
        and witness.stat().st_size > 0
    )
    citations = (
        Citation("playbook_digest", playbook_digest, _cited("playbook_digest") == playbook_digest),
        Citation("ration_card_digest", ration_card_ref, _cited("ration_card_digest") == ration_card_ref),
        Citation("queued_playbook_ref", queued_playbook_ref, _cited("queued_playbook_ref") == queued_playbook_ref),
        Citation("approval_ref", approval_ref, approval_verified),
    )

    ration = json.loads(ration_bytes)
    queue = json.loads(queue_bytes)
    item = queue["items"][0]

    scope = ScopeProjection(
        source_ref=ration_card_ref,
        # read scope: the QueuedPlaybook's allowed_paths (cited via queued_playbook_ref)
        allowed_read_paths=tuple(item.get("allowed_paths", ())),
        # write scope: the RationCard's narrower allowed_write_paths (source_ref)
        allowed_write_paths=tuple(ration.get("allowed_write_paths", ())),
        # forbidden fence: the QueuedPlaybook's forbidden_paths (cited via queued_playbook_ref)
        forbidden_paths=tuple(item.get("forbidden_paths", ())),
    )
    ration_proj = RationProjection(
        source_ref=ration_card_ref,
        network=bool(ration.get("network_allowed", False)),
        external_send=False,  # no RationCard axis; observe-only + network-locked ⇒ cannot send
        git=bool(ration.get("git_allowed", False)),
        doctrine_writes=bool(ration.get("doctrine_writes_allowed", False)),
        observe_only=bool(ration.get("output_is_observe_only", True)),
    )

    # admission_ref = re-verifiable seal over the admission basis.
    admission_ref = _seal_over(
        {
            "plan_ref": plan_ref,
            "citations": [c.as_dict() for c in citations],
        }
    )

    origin = Origin(
        submitted_by="operator",  # plan provenance.author; label only, not standing
        proposal_ref=plan_ref,
        playbook_ref=playbook_digest,
    )

    acceptance = Acceptance(
        required_checks=tuple(item.get("required_tests", ())),
        required_artifacts=("review_packet.manifest.json", "review_packet.summary.md"),
    )
    stop_conditions = tuple(item.get("stop_conditions", ()))

    routing = Routing(eligible_provider=fm.get("harness"))

    # PRODUCED testimony (the run already happened) — reference + status only.
    packet_path = d / "review_packet.manifest.json"
    produced = None
    if packet_path.exists():
        packet = json.loads(packet_path.read_bytes())
        produced = ProducedReceipts(
            review_packet_ref=sha256_ref_of_bytes(packet_path.read_bytes()),
            review_packet_status=packet.get("status"),
            run_session_id=CD4B_SESSION_ID,
            promotion_id=CD4B_PROMOTION_ID,
        )

    return project_work_container(
        work_id="wc-cd4-docs-normalize",
        admission_ref=admission_ref,
        origin=origin,
        intent=intent,
        scope_projection=scope,
        ration_projection=ration_proj,
        admission_basis=AdmissionBasis(citations=citations),
        capability_requirements=("file_read", "file_write", "shell_exec"),
        acceptance=acceptance,
        stop_conditions=stop_conditions,
        receipt_expectations=ReceiptExpectations(),
        routing=routing,
        produced_receipts=produced,
    )


__all__ = [
    "WORK_CONTAINER_SCHEMA_VERSION",
    "WorkContainerError",
    "UnverifiedCitationError",
    "MalformedAdmissionRefError",
    "DigestMismatchError",
    "sha256_ref_of_bytes",
    "Citation",
    "Origin",
    "ScopeProjection",
    "RationProjection",
    "Acceptance",
    "ReceiptExpectations",
    "Routing",
    "ProducedReceipts",
    "AdmissionBasis",
    "Custody",
    "WorkContainer",
    "verify_seal",
    "verify_container",
    "project_work_container",
    "project_cd4b_work_container",
    "CD4B_SESSION_ID",
    "CD4B_PROMOTION_ID",
    "CD4B_FENCED_FLIP_FILES",
]
