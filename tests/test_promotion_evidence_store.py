# SPDX-License-Identifier: Apache-2.0
"""P4.0c — ActivationReceipt store tests (one producer, one storage seam).

Roundtrip + content_hash stability, orphan (clean miss), and tamper refusal from
disk. The store is the IO seam for the chain root only — no observations, no
replay, no operator basis, no baseline, no N.
"""

from __future__ import annotations

import json

import pytest

from governor.clock_witness import MonotonicReading
from governor.promotion_evidence import ActivationReceipt
from governor.promotion_evidence_store import (
    ActivationReceiptStore,
    ActivationReceiptTamperError,
)

TUNABLE = "decomposition_size/max_slices"


def _activation(trial_id: str = "trial-1", trial_value=4) -> ActivationReceipt:
    return ActivationReceipt(
        trial_id=trial_id,
        tunable_name=TUNABLE,
        trial_value=trial_value,
        prior_baseline_value=8,
        activated_at=MonotonicReading(
            source="process_monotonic", epoch="boot:demo-single-host", ns=1_000
        ),
    )


# --- Roundtrip + content_hash stability --------------------------------------


def test_put_then_get_roundtrips(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    original = _activation()
    store.put(original)
    loaded = store.get("trial-1")
    assert loaded == original


def test_content_hash_stable_across_persist_load(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    original = _activation()
    before = original.content_hash
    store.put(original)
    loaded = store.get("trial-1")
    assert loaded is not None
    assert loaded.content_hash == before


def test_put_returns_path_under_layout(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation())
    assert path.exists()
    assert path.parent == tmp_path / "promotion_evidence" / "activations"
    assert store.list_trial_keys() == [path.stem]


# --- Orphan: a clean miss, not an error --------------------------------------


def test_get_unknown_trial_is_clean_miss(tmp_path):
    store = ActivationReceiptStore(tmp_path)
    assert store.get("never-activated") is None


# --- Tamper refusal from disk ------------------------------------------------


def test_tampered_field_with_stale_hash_is_refused(tmp_path):
    """Edit a field on disk but leave the stored content_hash → the recomputed
    hash no longer matches → refused."""
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation(trial_value=4))

    d = json.loads(path.read_text())
    d["trial_value"] = 99  # tamper: change the promoted value, keep old hash
    path.write_text(json.dumps(d, sort_keys=True, indent=2))

    with pytest.raises(ActivationReceiptTamperError):
        store.get("trial-1")


def test_tampered_hash_field_is_refused(tmp_path):
    """Corrupt the stored content_hash directly → mismatch → refused."""
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation())

    d = json.loads(path.read_text())
    d["content_hash"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(d, sort_keys=True, indent=2))

    with pytest.raises(ActivationReceiptTamperError):
        store.get("trial-1")


def test_trial_id_swapped_in_file_is_refused(tmp_path):
    """A file placed at trial-1's key but carrying a different trial_id (swap /
    key collision) is refused even if its own self-hash is internally consistent."""
    store = ActivationReceiptStore(tmp_path)
    path = store.put(_activation(trial_id="trial-1"))

    # Rebuild a *self-consistent* receipt for a different trial, write its bytes
    # into trial-1's file (so the self-hash passes but the trial_id check fails).
    other = _activation(trial_id="trial-OTHER")
    path.write_text(json.dumps(other.to_dict(), sort_keys=True, indent=2))

    with pytest.raises(ActivationReceiptTamperError):
        store.get("trial-1")


# --- The store integrates with the walk layer (round-tripped receipt binds) ---


def test_loaded_activation_hash_matches_for_observation_binding(tmp_path):
    """A persisted+loaded activation produces the same content_hash an observation
    must bind to — the store does not break walkability."""
    store = ActivationReceiptStore(tmp_path)
    original = _activation()
    store.put(original)
    loaded = store.get("trial-1")
    assert loaded is not None
    assert loaded.content_hash == original.content_hash
