"""Candidate annealing deltas — proposal custody, NO apply (P2.1).

Workflow-kernel campaign, Phase 2 (candidate-delta rung;
`working/campaign-workflow-kernel-annealing.md`,
`specs/gaps/GOV_GAP_ANNEALING_DELTA_001.md`). This is the first object that
*names a future mutation* — and it is still non-effective. An ``AnnealingDelta``
is a PROPOSAL: it describes a change to a tunable surface, carries the custody a
later admission step would need, and CANNOT apply anything. There is no apply
method, no activation, no config write, and no path to one in this module.

The fences are at construction:

* tunable surfaces are an **allowlist** (closed) — a delta may target only
  routing / budgets / decomposition size / retry posture / witness placement /
  default gates. Authority is allowlisted (zoning §3), never blocklisted.
* genesis-class surfaces (standing, linear_accountant, wicket, receipts,
  classification policy, doctrine, AG enforcement, kernel) are NEVER annealable
  — directional custody: a system may not rewrite the gates it acts through.
* four ``HardGuards`` are forced True and cannot be disabled.
* a delta MUST name a ``ControlBaseline`` reference, an expiry, and a rollback
  trigger, and MUST require human approval. Missing any → typed refusal.
* an LA-dependent delta with LA absent refuses ``requires_la_custody`` — the
  downgrade is visible, never faked (standalone rule).

Dependency direction (operator-pinned): this module does NOT import
``convergence_tuning`` (the domain tuning module) — generic annealing must not
depend on a domain module. It imports only pure helpers (``gate_receipt``
canonicalization) and no mutation-capable internals of any gate.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .gate_receipt import canonical_json, content_hash

# --------------------------------------------------------------------------- #
# Tunable-surface allowlist (closed) — the ONLY surfaces a delta may target.
# --------------------------------------------------------------------------- #

SURFACE_ROUTING = "routing"
SURFACE_BUDGETS = "budgets"
SURFACE_DECOMPOSITION_SIZE = "decomposition_size"
SURFACE_RETRY_POSTURE = "retry_posture"
SURFACE_WITNESS_PLACEMENT = "witness_placement"
SURFACE_DEFAULT_GATES = "default_gates"

TUNABLE_SURFACES = frozenset(
    {
        SURFACE_ROUTING,
        SURFACE_BUDGETS,
        SURFACE_DECOMPOSITION_SIZE,
        SURFACE_RETRY_POSTURE,
        SURFACE_WITNESS_PLACEMENT,
        SURFACE_DEFAULT_GATES,
    }
)

# Genesis-class surfaces (closed) — never annealable. A delta whose surface or
# target contains any of these as a SUBSTRING of the normalized (lowercase,
# alphanumeric-only) string is refused at construction (see _targets_genesis).
# These are atomic, distinctive words: 'linear_accountant' is matched via
# 'accountant', and short ambiguous abbreviations like 'la' are deliberately
# excluded (they collide with innocent words such as 'lane'). Best-effort
# defense-in-depth, NOT an activation-grade boundary — digit-internal evasions
# ('acc0untant') still slip; per-surface target allowlists are required before
# Phase 3 activation (see _targets_genesis note + the gap spec).
GENESIS_CLASS_SURFACES = frozenset(
    {
        "standing",
        "accountant",  # linear_accountant
        "wicket",
        "receipt",
        "receipts",
        "classification",  # classification_policy
        "doctrine",
        "enforcement",  # ag_enforcement
        "kernel",
        "custody",
    }
)

# --------------------------------------------------------------------------- #
# Closed refusal vocabulary
# --------------------------------------------------------------------------- #

REFUSE_TARGET_OFF_ALLOWLIST = "target_off_allowlist"
REFUSE_GENESIS_CLASS_TARGET = "genesis_class_target"
REFUSE_MISSING_BASELINE_REFERENCE = "missing_baseline_reference"
REFUSE_MISSING_EXPIRY = "missing_expiry"
REFUSE_MISSING_ROLLBACK_TRIGGER = "missing_rollback_trigger"
REFUSE_AUTO_APPLY_FORBIDDEN = "auto_apply_forbidden"
REFUSE_REQUIRES_LA_CUSTODY = "requires_la_custody"

CLOSED_DELTA_REFUSALS = frozenset(
    {
        REFUSE_TARGET_OFF_ALLOWLIST,
        REFUSE_GENESIS_CLASS_TARGET,
        REFUSE_MISSING_BASELINE_REFERENCE,
        REFUSE_MISSING_EXPIRY,
        REFUSE_MISSING_ROLLBACK_TRIGGER,
        REFUSE_AUTO_APPLY_FORBIDDEN,
        REFUSE_REQUIRES_LA_CUSTODY,
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase and strip every non-alphanumeric character.

    'linearAccountant2.pool' -> 'linearaccountant2pool';
    'AGEnforcement' -> 'agenforcement'. Casing, digits, and punctuation cannot
    be used to break a genesis term apart.
    """
    return _NON_ALNUM.sub("", text.lower())


def _targets_genesis(surface: str, target: str) -> bool:
    """True if a genesis-class term appears in the normalized surface or target.

    Substring match over a NORMALIZED string (not tokenization) against a set of
    DISTINCTIVE genesis words. This defeats the camelCase / ALLCAPS / digit-suffix
    evasions that whole-token matching missed ('linearaccountant2pool' contains
    'accountant'). 'la' is deliberately excluded from the set (it collides with
    innocent words like 'lane'); the remaining terms are distinctive enough that
    substring matching does not false-flag tunable knobs ('laneweights',
    'retrybudget' surface no genesis term).

    NOTE (future-slice — required before Phase 3 activation): this is a
    best-effort construction-time DETECTOR, acceptable for candidate/no-apply
    custody. It is NOT an activation-grade authority boundary — a normalized
    substring denylist can still over-refuse an oddly-named knob ('outstanding'
    contains 'standing') and is the wrong shape for *granting* authority. The
    surface allowlist is already the real authority gate; before any activation
    the free-form ``target`` must likewise be constrained by per-surface
    known-knob ALLOWLISTS (see specs/gaps/GOV_GAP_ANNEALING_DELTA_001.md).
    Doctrine: candidate deltas may use normalized genesis detection as
    defense-in-depth; activation requires actual target allowlists.
    """
    return any(
        g in _normalize(surface) or g in _normalize(target)
        for g in GENESIS_CLASS_SURFACES
    )


# --------------------------------------------------------------------------- #
# HardGuards — forced True, cannot be disabled
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class HardGuards:
    """The four things annealing may NEVER mutate. All forced True; a delta
    cannot be constructed with any of them disabled."""

    kernel_invariant_mutation_forbidden: bool = True
    refusal_semantics_mutation_forbidden: bool = True
    custody_mutation_forbidden: bool = True
    publication_rules_mutation_forbidden: bool = True

    def __post_init__(self) -> None:
        for name in (
            "kernel_invariant_mutation_forbidden",
            "refusal_semantics_mutation_forbidden",
            "custody_mutation_forbidden",
            "publication_rules_mutation_forbidden",
        ):
            if getattr(self, name) is not True:
                raise ValueError(
                    f"{name} is forced True; annealing may not disable a HardGuard"
                )


# --------------------------------------------------------------------------- #
# Typed refusal
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DeltaRefusal:
    """A typed, receiptable 'no' from :func:`propose_delta`. Carries a closed
    refusal code; produces no delta and touches nothing."""

    code: str
    detail: str
    offending: str | None = None

    def __post_init__(self) -> None:
        if self.code not in CLOSED_DELTA_REFUSALS:
            raise ValueError(
                f"code must be one of {sorted(CLOSED_DELTA_REFUSALS)}, "
                f"got {self.code!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "delta_refusal",
            "code": self.code,
            "detail": self.detail,
            "offending": self.offending,
        }


# --------------------------------------------------------------------------- #
# AnnealingDelta — the candidate proposal (non-effective; no apply)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AnnealingDelta:
    """A candidate adjustment to a tunable surface. A PROPOSAL only.

    Carries everything a later (Phase 3) admission would require — named
    baseline, expiry, rollback trigger, forced human approval, source
    observations — but has NO apply/activate method and no write path.
    ``__post_init__`` is defense-in-depth: even a hand construction that bypasses
    :func:`propose_delta` cannot produce a delta that is off-allowlist,
    genesis-targeting, guard-disabled, auto-applying, or missing a required
    custody field.
    """

    surface: str
    target: str
    change_summary: str
    baseline_id: str
    expiry: str
    rollback_trigger: str
    source_observation_ids: tuple[str, ...] = ()
    requires_human: bool = True
    la_dependent: bool = False
    la_custody_ref: str | None = None
    hard_guards: HardGuards = field(default_factory=HardGuards)

    def __post_init__(self) -> None:
        if self.surface not in TUNABLE_SURFACES:
            raise ValueError(
                f"surface must be in the tunable allowlist "
                f"{sorted(TUNABLE_SURFACES)}, got {self.surface!r}"
            )
        if _targets_genesis(self.surface, self.target):
            raise ValueError(
                f"target {self.target!r} names a genesis-class surface; "
                "annealing may not touch standing/LA/wicket/receipts/"
                "classification/doctrine/enforcement/kernel/custody"
            )
        if self.requires_human is not True:
            raise ValueError("requires_human is forced True; no auto-apply")
        for fname in ("baseline_id", "expiry", "rollback_trigger"):
            if not getattr(self, fname):
                raise ValueError(f"{fname} is mandatory and must be non-empty")
        # Defense-in-depth (not factory-only): a hand construction must not be
        # able to disable a guard or claim LA dependence without custody proof.
        if not isinstance(self.hard_guards, HardGuards):
            raise ValueError(
                "hard_guards must be a HardGuards instance (all guards forced True)"
            )
        # Re-verify the four booleans here too — the invariant is "all forced
        # True", so the delta asserts it after construction rather than trusting
        # HardGuards.__post_init__, closing even a forged (object.__setattr__)
        # instance that bypassed the frozen guard's own check.
        if not (
            self.hard_guards.kernel_invariant_mutation_forbidden
            and self.hard_guards.refusal_semantics_mutation_forbidden
            and self.hard_guards.custody_mutation_forbidden
            and self.hard_guards.publication_rules_mutation_forbidden
        ):
            raise ValueError(
                "all four HardGuards must be True; a delta cannot carry a "
                "disabled guard"
            )
        if self.la_dependent and not self.la_custody_ref:
            raise ValueError(
                "la_dependent delta must carry an la_custody_ref (proof of "
                "LA-backed custody); absent LA it must refuse, not fake it"
            )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": "annealing_delta_v0",
            "surface": self.surface,
            "target": self.target,
            "change_summary": self.change_summary,
            "baseline_id": self.baseline_id,
            "expiry": self.expiry,
            "rollback_trigger": self.rollback_trigger,
            "source_observation_ids": list(self.source_observation_ids),
            "requires_human": self.requires_human,
            "la_dependent": self.la_dependent,
            "la_custody_ref": self.la_custody_ref,
            # Read the actual guards (each is forced True by HardGuards, and the
            # field is validated to BE a HardGuards) — never hard-code, so the
            # canonical form cannot mask a malformed guard.
            "hard_guards": {
                "kernel_invariant_mutation_forbidden": (
                    self.hard_guards.kernel_invariant_mutation_forbidden
                ),
                "refusal_semantics_mutation_forbidden": (
                    self.hard_guards.refusal_semantics_mutation_forbidden
                ),
                "custody_mutation_forbidden": (
                    self.hard_guards.custody_mutation_forbidden
                ),
                "publication_rules_mutation_forbidden": (
                    self.hard_guards.publication_rules_mutation_forbidden
                ),
            },
        }

    @property
    def delta_id(self) -> str:
        return content_hash(canonical_json(self.canonical_dict()))

    def to_dict(self) -> dict[str, Any]:
        payload = self.canonical_dict()
        payload["delta_id"] = self.delta_id
        return payload

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> AnnealingDelta:
        """Reconstruct from a stored record. Pure (no IO). hard_guards is rebuilt
        as the default all-True HardGuards — a delta can never have been stored
        with a disabled guard (construction refuses it), so the default is the
        only valid value; the recomputed delta_id re-verifies integrity."""
        return cls(
            surface=d["surface"],
            target=d["target"],
            change_summary=d["change_summary"],
            baseline_id=d["baseline_id"],
            expiry=d["expiry"],
            rollback_trigger=d["rollback_trigger"],
            source_observation_ids=tuple(d.get("source_observation_ids", [])),
            requires_human=d.get("requires_human", True),
            la_dependent=d.get("la_dependent", False),
            la_custody_ref=d.get("la_custody_ref"),
        )


def propose_delta(
    *,
    surface: str,
    target: str,
    change_summary: str,
    baseline_id: str,
    expiry: str,
    rollback_trigger: str,
    source_observation_ids: tuple[str, ...] = (),
    requires_human: bool = True,
    la_dependent: bool = False,
    la_custody_ref: str | None = None,
) -> AnnealingDelta | DeltaRefusal:
    """Validate a proposed delta and return it, or a typed DeltaRefusal.

    Pure: constructs at most one frozen value, writes nothing, applies nothing.
    The graceful "no" path — a forbidden proposal returns a DeltaRefusal (so the
    refusal is receiptable) rather than raising, while a *direct* construction of
    a forbidden delta still raises via ``AnnealingDelta.__post_init__``.
    """
    if surface not in TUNABLE_SURFACES:
        return DeltaRefusal(
            REFUSE_TARGET_OFF_ALLOWLIST,
            f"surface {surface!r} is not in the tunable allowlist",
            offending=surface,
        )
    if _targets_genesis(surface, target):
        return DeltaRefusal(
            REFUSE_GENESIS_CLASS_TARGET,
            f"target {target!r} names a genesis-class surface (never annealable)",
            offending=target,
        )
    if not baseline_id:
        return DeltaRefusal(
            REFUSE_MISSING_BASELINE_REFERENCE,
            "a candidate delta must name a ControlBaseline reference",
        )
    if not expiry:
        return DeltaRefusal(
            REFUSE_MISSING_EXPIRY, "a candidate delta must carry an expiry"
        )
    if not rollback_trigger:
        return DeltaRefusal(
            REFUSE_MISSING_ROLLBACK_TRIGGER,
            "a candidate delta must carry a rollback trigger",
        )
    if requires_human is not True:
        return DeltaRefusal(
            REFUSE_AUTO_APPLY_FORBIDDEN,
            "human approval is forced; auto-apply is never admissible",
        )
    if la_dependent and not la_custody_ref:
        return DeltaRefusal(
            REFUSE_REQUIRES_LA_CUSTODY,
            "this delta declares LA-backed spend but carries no la_custody_ref; "
            "absent LA custody it must refuse or downgrade, never fake it",
        )
    return AnnealingDelta(
        surface=surface,
        target=target,
        change_summary=change_summary,
        baseline_id=baseline_id,
        expiry=expiry,
        rollback_trigger=rollback_trigger,
        source_observation_ids=tuple(source_observation_ids),
        requires_human=requires_human,
        la_dependent=la_dependent,
        la_custody_ref=la_custody_ref,
    )
