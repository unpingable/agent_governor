# SPDX-License-Identifier: Apache-2.0
"""P0 shadow pass — classify real promotion-evidence through the admission gate,
REPORT what would be quarantined/refused, change NOTHING.

This is the read-only move named (and explicitly *not authorized*) at the foot of
``working/P0-normal-form-closeout-2026-06-15.md``: run real promotion evidence
through ``normal_form.classify`` and report what the admission gate *would* do at the
promotion reliance point, **with no effect on decisions**. It is the witness P0
correctly does not yet have — the normal form's verdict goes from
``Normative<consistent-with-declared-spec>`` toward ``Observed`` by being exercised
against real evidence shapes rather than fixtures alone.

**Beside the path, never inside it.** This module imports the existing evidence
representation (``promotion_evidence`` / ``promotion_discovery``) and ``normal_form``;
it imports no write path, mints nothing, persists nothing, and never calls the
promotion gate. The gate's verdict, when shown side-by-side, is *passed through* —
recomputing it here would make this a second evaluator.

**Projection, not evaluation (the load-bearing distinction).** Each evidence receipt
has a *structural* epistemic species fixed by its TYPE, not inferred from its
contents:

    ActivationReceipt            -> OBSERVED     (a witnessed act: the activation occurred)
    LiveSurvivalObservationReceipt -> OBSERVED   (a witnessed in-bounds observation)
    ReplayHoldoutReceipt         -> OBSERVED     (a witnessed mechanical replay; NOT a
                                                  formal proof -- is_proof stays False)
    OperatorBasisReceipt         -> NORMATIVE    (valid under the operator's declared
                                                  authority -- authority, not world-fact)

The projector assigns species from the receipt class and copies the scope/freshness
the receipt already carries. It does NOT decide whether the evidence is good, fresh
enough, in-bounds, or sufficient — ``normal_form`` judges only the *legitimacy of the
conversion* (is this species being relied on as something it has not earned), while
``evaluate_promotion_from_evidence`` / ``derive_in_bounds`` still own every domain
fact. Conflating the two would be "quietly turning the adapter into a second
evaluator" — the one design hazard this module is built to avoid.

Provenance: P0 follow-on, 2026-06-16. Consumes P0 authority (``7923014`` normal-form
gate, ``76497ab`` closeout); does not co-author it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .normal_form import (
    AdmissionIntent,
    AdmissionStatus,
    ClaimManifest,
    ClaimSpecies,
    ClassificationResult,
    classify,
)
from .promotion_evidence import (
    ActivationReceipt,
    LiveSurvivalObservationReceipt,
    OperatorBasisReceipt,
    PromotionEvidenceBundle,
    ReplayHoldoutReceipt,
)
from .promotion_gate import PromotionEligibility

# The shadow alters nothing. This string is asserted on the report AND on every
# finding — a single hard invariant the tests pin (boundary 1).
SHADOW_DECISION_EFFECT = "none"

# The reliance point the shadow reports against: the gate that consumes promotion
# evidence. Naming it (not crossing it) mirrors normal_form's own discipline.
PROMOTION_RELIANCE_POINT = "promotion:evaluate_promotion_from_evidence"

# What the promotion path would be relying on each piece *as*: admissible promotion
# evidence (an OBSERVED-settled / authority-licensed input to the eligibility gate).
PROMOTION_ATTEMPTED_TARGET = "admissible_promotion_evidence"


# --- Projection table (structural, type-determined) ---------------------------
# Each projector maps a receipt to a ClaimManifest. The species is fixed by the
# receipt's class; scope/freshness are copied from what the receipt already carries.
# No presentation flag is set unless the promotion path genuinely presents the piece
# across a species boundary — and none of the four current types do, so a well-formed
# real bundle projects to licensed conversions (ADMITTED). The value of the shadow is
# the tripwire: a future evidence piece that DOES overclaim would surface here before
# being wired into reliance.


def project_activation(a: ActivationReceipt) -> ClaimManifest:
    """The chain root is a witnessed act (the activation occurred). OBSERVED, scoped to
    the tunable; the activation is a historical anchor, not a freshness-bound sample,
    so freshness is recorded but not required."""
    return ClaimManifest(
        species=ClaimSpecies.OBSERVED,
        value=f"activation:{a.trial_id}:{a.tunable_name}",
        scope=a.tunable_name,
        consumer="promotion",
        evidence_refs=(a.content_hash,),
        freshness=f"{a.activated_at.source}:{a.activated_at.epoch}:{a.activated_at.ns}",
        freshness_required=False,
    )


def project_observation(o: LiveSurvivalObservationReceipt) -> ClaimManifest:
    """A live-survival observation: OBSERVED, scoped to the trial, freshness-required
    (a survival observation that cannot prove its recency is not relied upon as
    survival evidence). The binding to the activation is its evidence_ref."""
    return ClaimManifest(
        species=ClaimSpecies.OBSERVED,
        value=f"observation:{o.observation_id}",
        scope=o.trial_id,
        consumer="promotion",
        evidence_refs=(o.activation_receipt_hash,),
        freshness=f"{o.observed_at.source}:{o.observed_at.epoch}:{o.observed_at.ns}",
        freshness_required=True,
    )


def project_replay(r: ReplayHoldoutReceipt) -> ClaimManifest:
    """The falsification witness: a mechanical replay over a frozen corpus. OBSERVED,
    scoped to the replay subject. **Honest non-promotion:** a non-regression replay is
    NOT a discharged formal proof (``is_proof`` stays False) and is NOT presented as
    system safety — so the proof->safety refusal correctly does not fire. It is a
    witnessed mechanical run, relied on as exactly that."""
    return ClaimManifest(
        species=ClaimSpecies.OBSERVED,
        value=f"replay:{r.replay_subject}",
        scope=r.replay_subject,
        consumer="promotion",
        evidence_refs=(r.corpus_hash, r.frozen_corpus_hash),
        freshness=None,
        freshness_required=False,
        is_proof=False,
        presented_as_system_safety=False,
    )


def project_operator_basis(b: OperatorBasisReceipt) -> ClaimManifest:
    """The operator's explicit promotion basis: NORMATIVE — valid under the operator's
    declared authority, not a world-fact. It is relied on AS authority, never promoted
    to fact, so it carries no presentation flag. (The red-line that auto-promotion is
    not a valid basis lives in the gate's ``promotion_operator_basis_claims_auto``, not
    here — that is a domain fact, the gate's to own.)"""
    return ClaimManifest(
        species=ClaimSpecies.NORMATIVE,
        value=f"operator_basis:{b.operator_actor}",
        scope=b.scope or None,
        consumer="promotion",
    )


@dataclass(frozen=True)
class ShadowFinding:
    """One evidence piece, classified at the promotion reliance point. ``present``
    distinguishes an absent piece (empty chamber) from a classified one; ``shadow_error``
    captures an adapter-side failure as observable data rather than an exception. In
    every case ``decision_effect`` is ``"none"`` — a finding never moves a decision."""

    evidence_kind: str  # "activation" | "observation:<id>" | "replay" | "operator_basis"
    evidence_identity: str  # content hash / stable id of the projected receipt
    present: bool
    declared_species: Optional[ClaimSpecies]
    attempted_target: str
    reliance_point: str
    classification: Optional[AdmissionStatus]
    reasons: tuple[str, ...] = ()
    scope: Optional[str] = None
    shadow_error: Optional[str] = None
    decision_effect: str = SHADOW_DECISION_EFFECT

    @property
    def would_refuse(self) -> bool:
        return self.classification is AdmissionStatus.REFUSED

    @property
    def would_quarantine(self) -> bool:
        return self.classification is AdmissionStatus.QUARANTINED


@dataclass(frozen=True)
class ShadowReport:
    """The shadow verdict: per-piece findings plus a *passed-through* mirror of the
    gate's actual verdict for side-by-side reading. The shadow computes the findings;
    it never computes (or alters) ``gate_eligible`` / ``gate_refusals``."""

    source: str
    trial_id: str
    findings: tuple[ShadowFinding, ...]
    gate_eligible: Optional[bool] = None
    gate_refusals: tuple[str, ...] = ()
    decision_effect: str = SHADOW_DECISION_EFFECT

    @property
    def would_refuse(self) -> tuple[ShadowFinding, ...]:
        return tuple(f for f in self.findings if f.would_refuse)

    @property
    def would_quarantine(self) -> tuple[ShadowFinding, ...]:
        return tuple(f for f in self.findings if f.would_quarantine)

    @property
    def shadow_errors(self) -> tuple[ShadowFinding, ...]:
        return tuple(f for f in self.findings if f.shadow_error is not None)


def _safe_project_and_classify(
    *,
    kind: str,
    identity: str,
    projector: Callable[[], ClaimManifest],
    intent: AdmissionIntent,
) -> ShadowFinding:
    """Project a single piece and classify it, catching ANY adapter-side failure into
    an observable ``shadow_error`` finding. An exception in projection must never
    escape the shadow (it would otherwise be mistaken for a promotion refusal — the
    shadow runs beside the path and owns no decision). Boundary 2."""
    try:
        manifest = projector()
        result: ClassificationResult = classify(manifest, intent=intent)
    except Exception as exc:  # noqa: BLE001 — adapter failure becomes data, not a raise
        return ShadowFinding(
            evidence_kind=kind,
            evidence_identity=identity,
            present=True,
            declared_species=None,
            attempted_target=PROMOTION_ATTEMPTED_TARGET,
            reliance_point=PROMOTION_RELIANCE_POINT,
            classification=None,
            shadow_error=f"{type(exc).__name__}: {exc}",
        )
    return ShadowFinding(
        evidence_kind=kind,
        evidence_identity=identity,
        present=True,
        declared_species=result.species,
        attempted_target=PROMOTION_ATTEMPTED_TARGET,
        reliance_point=PROMOTION_RELIANCE_POINT,
        classification=result.status,
        reasons=result.reasons,
        scope=result.scope,
    )


def _absent(kind: str) -> ShadowFinding:
    """A piece the bundle does not carry. Not a refusal — the shadow refuses nothing;
    absence is the gate's to refuse. Boundary 5 (empty chamber)."""
    return ShadowFinding(
        evidence_kind=kind,
        evidence_identity="",
        present=False,
        declared_species=None,
        attempted_target=PROMOTION_ATTEMPTED_TARGET,
        reliance_point=PROMOTION_RELIANCE_POINT,
        classification=None,
        reasons=("absent",),
    )


def shadow_classify_bundle(
    bundle: PromotionEvidenceBundle,
    *,
    eligibility: Optional[PromotionEligibility] = None,
    intent: AdmissionIntent = AdmissionIntent.RELIANCE,
    source: str = "<bundle>",
) -> ShadowReport:
    """Classify every piece of a promotion-evidence bundle through ``normal_form`` and
    report what would happen at the promotion reliance point. READ-ONLY: reads the
    bundle, writes nothing, calls no gate.

    ``intent`` defaults to ``RELIANCE`` because the reliance point (promotion) is real
    and named — the report shows what reliance *would* yield. ``eligibility``, if
    supplied, is mirrored verbatim for side-by-side reading; it is never recomputed or
    mutated here.
    """
    findings: list[ShadowFinding] = []

    if bundle.activation is None:
        findings.append(_absent("activation"))
    else:
        act = bundle.activation
        findings.append(
            _safe_project_and_classify(
                kind="activation",
                identity=act.content_hash,
                projector=lambda act=act: project_activation(act),
                intent=intent,
            )
        )

    if not bundle.observations:
        findings.append(_absent("observation"))
    else:
        for obs in bundle.observations:
            findings.append(
                _safe_project_and_classify(
                    kind=f"observation:{obs.observation_id}",
                    identity=obs.activation_receipt_hash,
                    projector=lambda obs=obs: project_observation(obs),
                    intent=intent,
                )
            )

    if bundle.replay is None:
        findings.append(_absent("replay"))
    else:
        rep = bundle.replay
        findings.append(
            _safe_project_and_classify(
                kind="replay",
                identity=f"{rep.trial_id}:{rep.replay_subject}:{rep.corpus_hash}",
                projector=lambda rep=rep: project_replay(rep),
                intent=intent,
            )
        )

    if bundle.operator_basis is None:
        findings.append(_absent("operator_basis"))
    else:
        ob = bundle.operator_basis
        findings.append(
            _safe_project_and_classify(
                kind="operator_basis",
                identity=f"{ob.trial_id}:{ob.operator_actor}",
                projector=lambda ob=ob: project_operator_basis(ob),
                intent=intent,
            )
        )

    return ShadowReport(
        source=source,
        trial_id=bundle.candidate.trial_id,
        findings=tuple(findings),
        gate_eligible=None if eligibility is None else eligibility.eligible,
        gate_refusals=() if eligibility is None else tuple(eligibility.refusals),
    )


def shadow_classify_discovered(
    discovered: "DiscoveredEvidence",  # noqa: F821 — runtime import avoidance
    *,
    intent: AdmissionIntent = AdmissionIntent.RELIANCE,
) -> ShadowReport:
    """Convenience: run the shadow over a ``DiscoveredEvidence`` (real on-disk receipts
    assembled by ``promotion_discovery``), mirroring the gate verdict that discovery
    already computed. The gate's eligibility is passed through, never recomputed."""
    return shadow_classify_bundle(
        discovered.bundle,
        eligibility=discovered.eligibility,
        intent=intent,
        source=discovered.source_root,
    )


__all__ = [
    "SHADOW_DECISION_EFFECT",
    "PROMOTION_RELIANCE_POINT",
    "PROMOTION_ATTEMPTED_TARGET",
    "ShadowFinding",
    "ShadowReport",
    "project_activation",
    "project_observation",
    "project_replay",
    "project_operator_basis",
    "shadow_classify_bundle",
    "shadow_classify_discovered",
]
