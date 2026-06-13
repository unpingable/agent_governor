"""Activation preflight — proves activation impossible until gates are real (P3.0).

Workflow-kernel campaign, Phase 3 opening slice
(`specs/gaps/GOV_GAP_RUNG_DEBT_COLLECTION_001.md`,
`specs/gaps/GOV_GAP_ANNEALING_DELTA_001.md`). This slice builds the gates that
keep activation IMPOSSIBLE; it activates nothing. There is no apply / activate /
config-write / rollback path here — only a checker that returns whether
activation *could* proceed, and refuses otherwise.

Two gates:

1. **Per-surface target ALLOWLISTS** (the real activation authority boundary).
   A delta is activation-eligible only if its ``target`` is in its surface's
   allowlist. A free-form target is refused. This **discharges
   P2_GENESIS_TARGET_ALLOWLIST_001 by mechanism, not prose**: the leaky
   candidate-time genesis *detector* (annealing.py) is defense-in-depth; ACTIVATION
   requires allowlist membership, which no spelling can evade.

2. **Rung-debt gate** (the conservation theorem at the activation seam). A
   ``RungDebt`` binds a future-rung obligation to a named collector. Activation
   refuses while any debt targeting the gated rung is open, self-collected
   (collector == the gated rung — a rung cannot clear its own gate), or has a
   broken source-boundary identity (the handoff from the recomposition seam was
   not accounted). The open-debt totality is computed by the SHARED
   ``account_boundaries`` combinator (pipeline_types) — a library, not a new
   authority: this module owns the eligibility decision; account_boundaries only
   does the accounting.

> Before the system may activate deltas, it must prove activation is gated by
> debts it cannot self-clear. Named is not collected; carried is not collected
> either.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .annealing import (
    SURFACE_BUDGETS,
    SURFACE_DECOMPOSITION_SIZE,
    SURFACE_DEFAULT_GATES,
    SURFACE_RETRY_POSTURE,
    SURFACE_ROUTING,
    SURFACE_WITNESS_PLACEMENT,
)
from .pipeline_types import (
    DISPOSITION_COMPLETED,
    VERDICT_ADMISSIBLE,
    account_boundaries,
)

# --------------------------------------------------------------------------- #
# Per-surface target allowlists (closed; the activation authority boundary)
# --------------------------------------------------------------------------- #
#
# Starter knob sets — representative, extensible by deliberate edit. The POINT is
# the mechanism (allowlist membership gates activation eligibility), not an
# exhaustive knob catalogue. A target outside its surface's set is refused at the
# activation seam regardless of how it is spelled — this is the allowlist that
# replaces the best-effort genesis denylist for activation purposes.
TARGET_ALLOWLISTS: dict[str, frozenset[str]] = {
    SURFACE_ROUTING: frozenset(
        {"lane_weights", "escalation_threshold", "fallback_order"}
    ),
    SURFACE_BUDGETS: frozenset(
        {"retry_budget", "capacity", "attention_budget", "time_budget"}
    ),
    SURFACE_DECOMPOSITION_SIZE: frozenset({"max_slices", "slice_cap"}),
    SURFACE_RETRY_POSTURE: frozenset(
        {"retry_budget", "backoff_base", "max_retries"}
    ),
    SURFACE_WITNESS_PLACEMENT: frozenset({"witness_seam", "early_witness"}),
    SURFACE_DEFAULT_GATES: frozenset({"recomposition_shadow", "shadow_emission"}),
}

# --------------------------------------------------------------------------- #
# Closed eligibility vocabulary
# --------------------------------------------------------------------------- #

ELIGIBLE = "eligible"
REFUSED_FREE_FORM_TARGET = "refused_free_form_target"
REFUSED_OPEN_NONDISCHARGE_CLAIM = "refused_open_nondischarge_claim"
REFUSED_SELF_COLLECTED = "refused_self_collected"
REFUSED_IDENTITY_BROKEN = "refused_identity_broken"

CLOSED_ELIGIBILITY = frozenset(
    {
        ELIGIBLE,
        REFUSED_FREE_FORM_TARGET,
        REFUSED_OPEN_NONDISCHARGE_CLAIM,
        REFUSED_SELF_COLLECTED,
        REFUSED_IDENTITY_BROKEN,
    }
)

# A parked-boundary / claim source id is content-addressed (sha256 hex).
_CONTENT_ID_RE = re.compile(r"^[0-9a-f]{64}$")


# --------------------------------------------------------------------------- #
# RungDebt — a bound future-rung obligation (not prose)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RungDebt:
    """Activation-gate view of a bound future-rung debt.

    Carries the rung-debt fields the activation gate needs and that the receipt
    kernel's ``NonDischargeClaim`` lacks (``target_rung`` / ``blocks_before`` /
    ``source_boundary_id``). A ``NonDischargeClaim``'s ``required_consumer`` /
    ``required_witness`` map to ``authorized_collector`` / ``discharge_witness``
    here; full unification onto the kernel type is a future kernel-ceremony item
    (NOT P3.0 — that would be a custody-affecting kernel change).

    ``__post_init__`` enforces the conservation theorem at bind time:
    ``authorized_collector != target_rung`` — a rung cannot be the authority that
    clears its own gate.
    """

    debt_id: str
    target_rung: str
    authorized_collector: str
    discharge_witness: str
    blocks_before: str
    source_boundary_id: str  # content-addressed; ties to the parked boundary
    discharged: bool = False

    def __post_init__(self) -> None:
        for fname in (
            "debt_id",
            "target_rung",
            "authorized_collector",
            "discharge_witness",
            "blocks_before",
            "source_boundary_id",
        ):
            if not getattr(self, fname):
                raise ValueError(f"{fname} is mandatory and must be non-empty")
        if self.authorized_collector == self.target_rung:
            raise ValueError(
                "authorized_collector must not equal target_rung — a rung cannot "
                "be the authority that clears its own gate (the authority that "
                "clears X cannot be X)"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "debt_id": self.debt_id,
            "target_rung": self.target_rung,
            "authorized_collector": self.authorized_collector,
            "discharge_witness": self.discharge_witness,
            "blocks_before": self.blocks_before,
            "source_boundary_id": self.source_boundary_id,
            "discharged": self.discharged,
        }


# --------------------------------------------------------------------------- #
# Eligibility result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EligibilityResult:
    """Outcome of a preflight check. ``eligible`` means activation COULD proceed
    (nothing is activated here); any other verdict means activation is refused."""

    verdict: str
    detail: str = ""
    offending: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in CLOSED_ELIGIBILITY:
            raise ValueError(
                f"verdict must be one of {sorted(CLOSED_ELIGIBILITY)}, "
                f"got {self.verdict!r}"
            )

    @property
    def eligible(self) -> bool:
        return self.verdict == ELIGIBLE


def target_eligible(surface: str, target: str) -> bool:
    """True iff target is in its surface's activation allowlist. Pure."""
    return target in TARGET_ALLOWLISTS.get(surface, frozenset())


def check_activation_eligibility(
    *,
    surface: str,
    target: str,
    target_rung: str,
    debts: Sequence[RungDebt] = (),
    parked_boundary_ids: frozenset[str] | None = None,
) -> EligibilityResult:
    """Preflight ONLY. Returns whether activation COULD proceed; activates nothing.

    Pure — no IO, no write, no apply. Refuses (activation impossible) when:

    * target is not in its surface's allowlist          → free_form_target
    * a debt targeting this rung is self-collected       → self_collected
    * a debt's source-boundary identity is broken/absent → identity_broken
    * any debt targeting this rung is open (undischarged) → open_nondischarge_claim

    Refusal precedence is most-structural-first; the open-debt totality is
    delegated to the shared ``account_boundaries`` combinator.
    """
    # Gate 1 — target allowlist (discharges P2_GENESIS_TARGET_ALLOWLIST_001).
    if not target_eligible(surface, target):
        return EligibilityResult(
            REFUSED_FREE_FORM_TARGET,
            f"target {target!r} is not in the {surface!r} activation allowlist",
            (target,),
        )

    relevant = [d for d in debts if d.target_rung == target_rung]

    # Gate 2 — self-collection (re-checked at the gate even though RungDebt
    # refuses it at construction; defends against a forged debt).
    self_collected = tuple(
        d.debt_id for d in relevant if d.authorized_collector == target_rung
    )
    if self_collected:
        return EligibilityResult(
            REFUSED_SELF_COLLECTED,
            "a debt gating this rung names the gated rung as its own collector",
            self_collected,
        )

    # Gate 3 — handoff identity, checked on the debts whose discharge we would
    # otherwise TRUST. Fail closed: a discharged debt is identity-proven only if
    # its source is a clean content id AND is present in an explicitly-supplied
    # parked-boundary set. ``parked_boundary_ids is None`` means the carry was
    # never witnessed → unproven → broken (no silent ELIGIBLE on an unwitnessed
    # carry). An OPEN debt's identity is moot — it is refused as open below.
    def _identity_proven(d: RungDebt) -> bool:
        return (
            _CONTENT_ID_RE.match(d.source_boundary_id) is not None
            and parked_boundary_ids is not None
            and d.source_boundary_id in parked_boundary_ids
        )

    broken = tuple(
        d.debt_id for d in relevant if d.discharged and not _identity_proven(d)
    )
    if broken:
        return EligibilityResult(
            REFUSED_IDENTITY_BROKEN,
            "a discharged debt's source-boundary carry is malformed or unwitnessed",
            broken,
        )

    # Gate 4 — open-debt totality via the shared combinator, over UNIQUE
    # per-occurrence keys so a discharged debt cannot mask an open debt that
    # happens to share its id. Every occurrence is an admitted obligation;
    # a discharged (and, by gate 3, identity-proven) occurrence is accounted; an
    # open occurrence is unaccounted → account_boundaries refuses → refused.
    keyed = [(f"{i}:{d.debt_id}", d) for i, d in enumerate(relevant)]
    admitted = [key for key, _ in keyed]
    accounted = {
        key: DISPOSITION_COMPLETED for key, d in keyed if d.discharged
    }
    acct = account_boundaries(admitted, accounted)
    if acct.verdict != VERDICT_ADMISSIBLE:
        open_ids = tuple(key.split(":", 1)[1] for key in acct.unaccounted)
        return EligibilityResult(
            REFUSED_OPEN_NONDISCHARGE_CLAIM,
            "an open debt targets this rung and is not discharged",
            open_ids,
        )

    return EligibilityResult(ELIGIBLE)
