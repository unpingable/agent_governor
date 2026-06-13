"""Specimens for control baselines (P2.2; registry only).

The red line under test: a ControlBaseline exists ONLY via explicit admission
(a creation receipt), never auto-minted from a session promotion. The registry
writes baseline RECORDS only — no apply/activate/rollback, no config write.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from governor import control_baseline as cb
from governor.control_baseline import (
    ControlBaseline,
    ControlBaselineStore,
    admit_baseline,
)


def _admit(**over):
    base = dict(
        name="b0",
        config_hashes={"retry_budget": "sha256:" + "a" * 64},
        creation_receipt_id="rcpt_admit_1",
        admitted_by="operator",
    )
    base.update(over)
    return admit_baseline(**base)


# --------------------------------------------------------------------------- #
# The red line: admission-only, no auto-mint
# --------------------------------------------------------------------------- #


class TestAdmissionOnly:
    def test_creation_receipt_id_is_mandatory(self) -> None:
        with pytest.raises(ValueError, match="creation_receipt_id is mandatory"):
            admit_baseline(
                name="b0",
                config_hashes={},
                creation_receipt_id="",
                admitted_by="operator",
            )

    def test_name_mandatory(self) -> None:
        with pytest.raises(ValueError, match="name must be non-empty"):
            admit_baseline(
                name="",
                config_hashes={},
                creation_receipt_id="r",
                admitted_by="operator",
            )

    def test_admitted_by_mandatory(self) -> None:
        with pytest.raises(ValueError, match="admitted_by is mandatory"):
            admit_baseline(
                name="b0",
                config_hashes={},
                creation_receipt_id="r",
                admitted_by="",
            )

    def test_module_does_not_import_session_continuity(self) -> None:
        # Red line: no path from session promotion to baseline mint. The module
        # stores a checkpoint_ref STRING, never a live session.
        for line in Path(cb.__file__).read_text().splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")):
                assert "session_continuity" not in s, s


# --------------------------------------------------------------------------- #
# No activation / no mutation surface
# --------------------------------------------------------------------------- #


class TestNoActivationSurface:
    _MUTATION_VERBS = ("apply", "activate", "rollback", "promote", "execute")

    def test_store_has_no_activation_method(self) -> None:
        for name in dir(ControlBaselineStore):
            if name.startswith("_"):
                continue
            assert not any(v in name.lower() for v in self._MUTATION_VERBS), name

    def test_module_has_no_activation_function(self) -> None:
        for name, obj in vars(cb).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            assert not any(v in name.lower() for v in self._MUTATION_VERBS), name


# --------------------------------------------------------------------------- #
# Content-addressed identity
# --------------------------------------------------------------------------- #


class TestIdentity:
    def test_baseline_id_deterministic(self) -> None:
        a = _admit()
        b = _admit()
        assert a.baseline_id == b.baseline_id
        assert len(a.baseline_id) == 64

    def test_identity_excludes_admission_metadata(self) -> None:
        # Same rollback target content, different admission receipt -> SAME
        # baseline_id (identity is content, not the admission event).
        a = _admit(creation_receipt_id="rcpt_1", admitted_by="alice")
        b = _admit(creation_receipt_id="rcpt_2", admitted_by="bob")
        assert a.baseline_id == b.baseline_id

    def test_identity_order_independent_all_paths(self) -> None:
        # Content-addressing must hold regardless of construction path or pair
        # order: direct construction and from_dict with reordered config_hashes
        # produce the SAME baseline_id (normalization lives on the type).
        pairs_a = (("alpha", "sha256:" + "1" * 64), ("beta", "sha256:" + "2" * 64))
        pairs_b = (("beta", "sha256:" + "2" * 64), ("alpha", "sha256:" + "1" * 64))
        a = ControlBaseline(
            name="b", config_hashes=pairs_a, creation_receipt_id="r", admitted_by="o"
        )
        b = ControlBaseline(
            name="b", config_hashes=pairs_b, creation_receipt_id="r", admitted_by="o"
        )
        assert a.baseline_id == b.baseline_id
        # from_dict path too.
        restored = ControlBaseline.from_dict(
            {
                "name": "b",
                "config_hashes": [list(p) for p in pairs_b],
                "creation_receipt_id": "r",
                "admitted_by": "o",
            }
        )
        assert restored.baseline_id == a.baseline_id

    def test_different_config_different_id(self) -> None:
        a = _admit(config_hashes={"retry_budget": "sha256:" + "a" * 64})
        b = _admit(config_hashes={"retry_budget": "sha256:" + "b" * 64})
        assert a.baseline_id != b.baseline_id

    def test_to_dict_carries_id_and_metadata(self) -> None:
        a = _admit()
        d = a.to_dict()
        assert d["baseline_id"] == a.baseline_id
        assert d["schema"] == "control_baseline_v0"
        assert d["creation_receipt_id"] == "rcpt_admit_1"

    def test_from_dict_roundtrip(self) -> None:
        a = _admit(supersedes="cb_prev", checkpoint_ref="chk_7")
        restored = ControlBaseline.from_dict(a.to_dict())
        assert restored.baseline_id == a.baseline_id
        assert restored.supersedes == "cb_prev"
        assert restored.checkpoint_ref == "chk_7"


# --------------------------------------------------------------------------- #
# Registry / store (record-keeping only)
# --------------------------------------------------------------------------- #


class TestStore:
    def test_put_get_roundtrip(self, tmp_path) -> None:
        store = ControlBaselineStore(tmp_path)
        a = _admit()
        store.put(a)
        got = store.get(a.baseline_id)
        assert got is not None
        assert got.baseline_id == a.baseline_id

    def test_get_missing_returns_none(self, tmp_path) -> None:
        assert ControlBaselineStore(tmp_path).get("nope") is None

    def test_list_ids(self, tmp_path) -> None:
        store = ControlBaselineStore(tmp_path)
        store.put(_admit(config_hashes={"k": "sha256:" + "a" * 64}))
        store.put(_admit(config_hashes={"k": "sha256:" + "b" * 64}))
        assert len(store.list_ids()) == 2

    def test_put_writes_only_under_baseline_dir(self, tmp_path) -> None:
        # Path fence: record-writes land only in control_baselines/, nowhere else.
        store = ControlBaselineStore(tmp_path)
        path = store.put(_admit())
        assert path.parent == tmp_path / "control_baselines"
        # Only the baseline dir was created at the root.
        assert [p.name for p in tmp_path.iterdir()] == ["control_baselines"]

    def test_store_has_no_delete(self, tmp_path) -> None:
        # Deletion + reference-counting is Phase 3a (once deltas can reference a
        # baseline); not present in this slice.
        assert not hasattr(ControlBaselineStore, "delete")


# --------------------------------------------------------------------------- #
# Lineage / bisectability
# --------------------------------------------------------------------------- #


class TestLineage:
    def test_supersedes_roundtrips_and_is_diffable(self) -> None:
        b0 = _admit(name="b0", config_hashes={"retry_budget": "sha256:" + "a" * 64})
        b1 = _admit(
            name="b1",
            config_hashes={"retry_budget": "sha256:" + "c" * 64},
            supersedes=b0.baseline_id,
        )
        assert b1.supersedes == b0.baseline_id
        # Bisectability: the diff between two baselines is reconstructable from
        # their config hashes alone — no re-run needed.
        assert dict(b0.config_hashes) != dict(b1.config_hashes)
