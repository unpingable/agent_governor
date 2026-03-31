# Gap Spec: Vocabulary Erosion Detection (Δh↔Δn Loop)

**Status:** proposed (v3 — do not build now)
**Affects:** continuity anchors, claim_diff, drift detection
**Date:** 2026-03-31
**Origin:** cybernetic failure taxonomy — Δh↔Δn reinforcing loop

## Problem

The Δh↔Δn loop: normalization erases vocabulary for baseline; lost vocabulary makes non-return invisible. In Governor terms: if anchors/decisions normalize a bad state and the vocabulary for "before" is lost, claim_diff can't detect the drift because there's nothing to diff against.

Current `claim_diff.py` requires that the vocabulary was captured in a prior snapshot. If the vocabulary was never there, or was overwritten during normalization, the drift is invisible.

## Proposed (v3)

Periodic anchor inventory with content hash. Detect when anchor descriptions or forbidden patterns change without explicit revision events.

- Hash the full anchor registry periodically (per session or per N turns)
- Store anchor inventory hashes in a ledger
- Detect: anchor set changed between inventories without a corresponding `anchor add/remove/upgrade` event
- Surface as a "vocabulary drift" signal distinct from claim drift

## Why Not Now

This requires changes to how anchor mutations are tracked and a new ledger for inventory hashes. It's interpretive infrastructure, not operational plumbing. The override accumulation signal is more immediately useful.

## Dependencies

- `continuity.py` (AnchorRegistry)
- `claim_diff.py` (snapshot comparison)
