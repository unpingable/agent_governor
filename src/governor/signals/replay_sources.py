# SPDX-License-Identifier: Apache-2.0
"""
Replay source adapters — prepare input data for the replay harness.

Adapters for:
  - Envelope bundles (group A-signal envelopes by window for B1 replay)
  - Receipt bundles (group receipt records by window for B2 replay)

No business logic here — just grouping and shaping.

Design authority: specs/gaps/V2_4C_SPINE.md §2.2
"""

from __future__ import annotations

from typing import Any

from .envelope import SignalEnvelope, canonical_json, content_hash
from .replay_harness import ReplayManifest, ReplayWindowInput


# ── Envelope replay sources ──────────────────────────────────────────────────

def prepare_envelope_windows(
    source_envelopes: list[dict[str, Any]],
    target_signal: str,
    target_signal_version: int = 1,
    *,
    input_signal_ids: frozenset[str] | None = None,
) -> tuple[list[ReplayWindowInput], ReplayManifest]:
    """Group stored envelopes by window for envelope-mode replay.

    Separates envelopes into:
      - Input signals (used to re-derive the target)
      - Original outputs (target signal, for comparison)

    Groups by (window_start, window_end, window_kind).

    Args:
        source_envelopes: List of envelope dicts (from JSONL or store).
        target_signal: Signal ID to replay (e.g. "CAPTURE_SELF_DIAGNOSTIC").
        target_signal_version: Signal version to replay.
        input_signal_ids: Which signal IDs are inputs to the target.
            If None, all non-target signals are treated as inputs.

    Returns:
        (replay_windows, manifest)
    """
    # Separate target originals from input signals
    originals: dict[tuple[str, str, str], dict[str, Any]] = {}
    inputs_by_window: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}

    all_hashes: list[str] = []

    for env_dict in source_envelopes:
        sig_id = env_dict.get("signal_id", "")
        ws = env_dict.get("window_start", "")
        we = env_dict.get("window_end", "")
        wk = env_dict.get("window_kind", "")

        if not ws or not we:
            continue

        key = (ws, we, wk)
        env_hash = content_hash(canonical_json(env_dict))
        all_hashes.append(env_hash)

        if sig_id == target_signal:
            originals[key] = env_dict
        elif input_signal_ids is None or sig_id in input_signal_ids:
            inputs_by_window.setdefault(key, {})[sig_id] = env_dict

    # Build replay windows
    all_keys = sorted(set(list(originals.keys()) + list(inputs_by_window.keys())))
    windows: list[ReplayWindowInput] = []

    for key in all_keys:
        ws, we, wk = key
        windows.append(ReplayWindowInput(
            window_start=ws,
            window_end=we,
            window_kind=wk,
            signal_id=target_signal,
            signal_version=target_signal_version,
            envelope_inputs=inputs_by_window.get(key),
            original_output=originals.get(key),
        ))

    manifest = ReplayManifest.build(all_hashes, source_mode="envelope")
    return windows, manifest


# ── Receipt replay sources ───────────────────────────────────────────────────

def prepare_receipt_windows(
    receipts: list[dict[str, Any]],
    original_envelopes: list[dict[str, Any]],
    target_signal: str,
    target_signal_version: int = 1,
    *,
    window_boundaries: list[tuple[str, str, str]] | None = None,
) -> tuple[list[ReplayWindowInput], ReplayManifest]:
    """Prepare receipt-mode replay windows.

    For receipt replay, window boundaries come from either:
      - Explicit list (window_boundaries parameter)
      - Extracted from original_envelopes (window_start/window_end/window_kind)

    Receipts are grouped into windows by timestamp (inclusive start,
    exclusive end), matching production window semantics.  Pre-window
    receipts are also included (for evidence linking).

    Args:
        receipts: List of receipt record dicts.
        original_envelopes: Original signal envelopes for comparison.
        target_signal: Signal ID to replay.
        target_signal_version: Signal version.
        window_boundaries: Explicit (start, end, kind) tuples.

    Returns:
        (replay_windows, manifest)
    """
    # Build originals index
    originals: dict[tuple[str, str, str], dict[str, Any]] = {}
    for env_dict in original_envelopes:
        if env_dict.get("signal_id") != target_signal:
            continue
        ws = env_dict.get("window_start", "")
        we = env_dict.get("window_end", "")
        wk = env_dict.get("window_kind", "")
        if ws and we:
            originals[(ws, we, wk)] = env_dict

    # Determine window boundaries
    if window_boundaries is None:
        boundaries = sorted(originals.keys())
    else:
        boundaries = sorted(window_boundaries)

    # Content hashes for manifest
    all_hashes: list[str] = []
    for r in receipts:
        all_hashes.append(content_hash(canonical_json(r)))
    for env in original_envelopes:
        all_hashes.append(content_hash(canonical_json(env)))

    # Group receipts into windows
    windows: list[ReplayWindowInput] = []
    for ws, we, wk in boundaries:
        # Include receipts in window (start <= ts < end) and pre-window
        window_receipts = []
        for r in receipts:
            ts = r.get("timestamp", "")
            if ts < we:  # in window or pre-window
                window_receipts.append(r)

        windows.append(ReplayWindowInput(
            window_start=ws,
            window_end=we,
            window_kind=wk,
            signal_id=target_signal,
            signal_version=target_signal_version,
            receipt_inputs=tuple(window_receipts),
            original_output=originals.get((ws, we, wk)),
        ))

    manifest = ReplayManifest.build(all_hashes, source_mode="receipt")
    return windows, manifest
