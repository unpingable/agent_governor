"""Specimens for candidate annealing deltas (P2.1).

Phase 2 introduces the first object that NAMES a future mutation. It must remain
non-effective: no apply path, no config write, no way to construct a delta that
targets a forbidden surface or disables a guard. These tests weight those
fences; classification of "where a delta might look" is secondary.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from governor import annealing as an
from governor.annealing import (
    REFUSE_AUTO_APPLY_FORBIDDEN,
    REFUSE_GENESIS_CLASS_TARGET,
    REFUSE_MISSING_BASELINE_REFERENCE,
    REFUSE_MISSING_EXPIRY,
    REFUSE_MISSING_ROLLBACK_TRIGGER,
    REFUSE_REQUIRES_LA_CUSTODY,
    REFUSE_TARGET_OFF_ALLOWLIST,
    TUNABLE_SURFACES,
    AnnealingDelta,
    DeltaRefusal,
    HardGuards,
    propose_delta,
)


def _ok(**over):
    base = dict(
        surface="retry_posture",
        target="retry_budget",
        change_summary="lower default retry budget",
        baseline_id="cb_abc",
        expiry="2026-06-20T00:00:00Z",
        rollback_trigger="refusal_rate>0.2",
    )
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# No-apply / no-write fences (PRIMARY)
# --------------------------------------------------------------------------- #


class TestNoApplyPath:
    _WRITE_VERBS = (
        "apply",
        "activate",
        "commit",
        "write",
        "persist",
        "save",
        "mutate",
        "execute",
        "rollback",
        "promote",
    )

    def test_module_exposes_no_apply_or_write_callable(self) -> None:
        for name, obj in vars(an).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            lowered = name.lower()
            assert not any(v in lowered for v in self._WRITE_VERBS), name

    def test_delta_has_no_apply_method(self) -> None:
        for name in dir(AnnealingDelta):
            if name.startswith("_"):
                continue
            assert not any(v in name.lower() for v in self._WRITE_VERBS), name

    def test_source_has_no_write_primitives(self) -> None:
        # Grep-fence: the module's source contains no file/IO write primitive.
        src = Path(an.__file__).read_text()
        for needle in ("open(", ".write(", "Path(", "os.", "json.dump"):
            assert needle not in src, needle


# --------------------------------------------------------------------------- #
# Allowlist + genesis fences
# --------------------------------------------------------------------------- #


class TestSurfaceFences:
    def test_each_tunable_surface_accepted(self) -> None:
        for surface in TUNABLE_SURFACES:
            d = propose_delta(**_ok(surface=surface, target="some_knob"))
            assert isinstance(d, AnnealingDelta)
            assert d.surface == surface

    def test_off_allowlist_surface_refused(self) -> None:
        r = propose_delta(**_ok(surface="anything_else"))
        assert isinstance(r, DeltaRefusal)
        assert r.code == REFUSE_TARGET_OFF_ALLOWLIST

    @pytest.mark.parametrize(
        "target",
        [
            "standing/horizon",
            "wicket_admission",
            "linear_accountant.pool",
            "linearAccountant.pool",  # camelCase must not evade
            "linearAccountant2.pool",  # camelCase + digit suffix
            "LINEARACCOUNTANT.pool",  # ALLCAPS concatenation
            "classification_policy",
            "classificationPolicy",  # camelCase
            "ag_enforcement",
            "agEnforcement",  # camelCase
            "AGEnforcement",  # ALLCAPS-ish acronym prefix
            "receipts",
            "receipt_store",
            "doctrine_rule",
            "kernel_invariant",
            "custody_chain",
        ],
    )
    def test_genesis_class_target_refused(self, target: str) -> None:
        r = propose_delta(**_ok(target=target))
        assert isinstance(r, DeltaRefusal)
        assert r.code == REFUSE_GENESIS_CLASS_TARGET

    @pytest.mark.parametrize(
        "surface,target",
        [
            ("budgets", "retry_budget"),
            ("routing", "lane_weights"),
            ("routing", "laneweights"),
            ("budgets", "retrybudget"),
            ("decomposition_size", "max_slices"),
            ("witness_placement", "early_witness"),  # 'witness' != 'wicket'
        ],
    )
    def test_innocent_target_not_false_flagged(self, surface, target) -> None:
        # Normalized substring detection must not trip on innocent knobs: the
        # distinctive genesis terms (with 'la' excluded) appear in none of these.
        d = propose_delta(**_ok(surface=surface, target=target))
        assert isinstance(d, AnnealingDelta)


# --------------------------------------------------------------------------- #
# Mandatory-custody refusals
# --------------------------------------------------------------------------- #


class TestMandatoryCustody:
    def test_missing_baseline_refused(self) -> None:
        r = propose_delta(**_ok(baseline_id=""))
        assert isinstance(r, DeltaRefusal)
        assert r.code == REFUSE_MISSING_BASELINE_REFERENCE

    def test_missing_expiry_refused(self) -> None:
        r = propose_delta(**_ok(expiry=""))
        assert r.code == REFUSE_MISSING_EXPIRY

    def test_missing_rollback_trigger_refused(self) -> None:
        r = propose_delta(**_ok(rollback_trigger=""))
        assert r.code == REFUSE_MISSING_ROLLBACK_TRIGGER

    def test_auto_apply_refused(self) -> None:
        r = propose_delta(**_ok(requires_human=False))
        assert r.code == REFUSE_AUTO_APPLY_FORBIDDEN

    def test_la_dependent_without_custody_ref_refused(self) -> None:
        r = propose_delta(**_ok(la_dependent=True))
        assert r.code == REFUSE_REQUIRES_LA_CUSTODY

    def test_la_dependent_with_custody_ref_ok(self) -> None:
        d = propose_delta(**_ok(la_dependent=True, la_custody_ref="la_grant_7"))
        assert isinstance(d, AnnealingDelta)
        assert d.la_dependent is True
        assert d.la_custody_ref == "la_grant_7"


# --------------------------------------------------------------------------- #
# HardGuards + defense-in-depth construction
# --------------------------------------------------------------------------- #


class TestHardGuardsAndConstruction:
    def test_hard_guards_all_default_true(self) -> None:
        g = HardGuards()
        assert g.kernel_invariant_mutation_forbidden is True
        assert g.custody_mutation_forbidden is True

    def test_hard_guard_cannot_be_disabled(self) -> None:
        with pytest.raises(ValueError, match="forced True"):
            HardGuards(custody_mutation_forbidden=False)

    def test_forged_disabled_guard_refused_by_delta(self) -> None:
        # Even a HardGuards forged past its own frozen __post_init__ (via
        # object.__setattr__) is refused: AnnealingDelta re-checks the four
        # booleans rather than trusting the type alone.
        g = HardGuards()
        object.__setattr__(g, "custody_mutation_forbidden", False)
        with pytest.raises(ValueError, match="all four HardGuards must be True"):
            AnnealingDelta(
                surface="routing",
                target="lane_weights",
                change_summary="x",
                baseline_id="cb",
                expiry="e",
                rollback_trigger="t",
                hard_guards=g,
            )

    def test_direct_construction_off_allowlist_raises(self) -> None:
        with pytest.raises(ValueError, match="tunable allowlist"):
            AnnealingDelta(
                surface="nope",
                target="k",
                change_summary="x",
                baseline_id="cb",
                expiry="e",
                rollback_trigger="t",
            )

    def test_direct_construction_genesis_raises(self) -> None:
        with pytest.raises(ValueError, match="genesis-class"):
            AnnealingDelta(
                surface="routing",
                target="standing_route",
                change_summary="x",
                baseline_id="cb",
                expiry="e",
                rollback_trigger="t",
            )

    def test_direct_construction_auto_apply_raises(self) -> None:
        with pytest.raises(ValueError, match="requires_human is forced"):
            AnnealingDelta(
                surface="routing",
                target="lane_weights",
                change_summary="x",
                baseline_id="cb",
                expiry="e",
                rollback_trigger="t",
                requires_human=False,
            )

    def test_direct_construction_missing_field_raises(self) -> None:
        with pytest.raises(ValueError, match="mandatory"):
            AnnealingDelta(
                surface="routing",
                target="lane_weights",
                change_summary="x",
                baseline_id="",
                expiry="e",
                rollback_trigger="t",
            )

    def test_direct_construction_bad_hard_guards_raises(self) -> None:
        # Backstop: a hand construction cannot smuggle in a non-HardGuards
        # (e.g. None) and have canonical_dict mask it as all-True.
        with pytest.raises(ValueError, match="HardGuards"):
            AnnealingDelta(
                surface="routing",
                target="lane_weights",
                change_summary="x",
                baseline_id="cb",
                expiry="e",
                rollback_trigger="t",
                hard_guards=None,  # type: ignore[arg-type]
            )

    def test_direct_construction_la_dependent_without_ref_raises(self) -> None:
        # Backstop: la_dependent is structural — no custody ref, no delta, even
        # via direct construction (not just the factory).
        with pytest.raises(ValueError, match="la_custody_ref"):
            AnnealingDelta(
                surface="routing",
                target="lane_weights",
                change_summary="x",
                baseline_id="cb",
                expiry="e",
                rollback_trigger="t",
                la_dependent=True,
            )


# --------------------------------------------------------------------------- #
# Identity + serialization
# --------------------------------------------------------------------------- #


class TestIdentity:
    def test_delta_id_deterministic(self) -> None:
        a = propose_delta(**_ok())
        b = propose_delta(**_ok())
        assert isinstance(a, AnnealingDelta) and isinstance(b, AnnealingDelta)
        assert a.delta_id == b.delta_id
        assert len(a.delta_id) == 64

    def test_to_dict_carries_id_and_guards(self) -> None:
        d = propose_delta(**_ok())
        payload = d.to_dict()
        assert payload["delta_id"] == d.delta_id
        assert payload["schema"] == "annealing_delta_v0"
        assert payload["hard_guards"]["custody_mutation_forbidden"] is True

    def test_refusal_rejects_unknown_code(self) -> None:
        with pytest.raises(ValueError, match="code must be one of"):
            DeltaRefusal(code="whatever", detail="x")

    def test_does_not_import_convergence_tuning(self) -> None:
        # Dependency direction: generic annealing must not depend on the domain
        # tuning module. Check IMPORT statements only (the docstring is allowed
        # to name the rule).
        for line in Path(an.__file__).read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "convergence_tuning" not in stripped, stripped
