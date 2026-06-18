# SPDX-License-Identifier: Apache-2.0
"""
Receipt transparency — a transparent receipt log (CT / Rekor-shaped, NOT
blockchain).

Skeleton layer per ``specs/gaps/GOV_GAP_RECEIPT_TRANSPARENCY_001.md``: committed
epoch roots, compact inclusion proofs, consistency / fork evidence, and ordering
authority — plus the firewall guards that keep them from being mistaken for
authority. No accumulator, no proof verification, no live behavior yet.

The word "blockchain" appears in this package only in non-claim warnings. The
primitive is a transparent receipt log with compact membership and fork
evidence, not a distributed ledger.
"""

from __future__ import annotations

from governor.receipt_transparency.types import (
    FIREWALL,
    NO_OPERATIONAL_EFFECT,
    AccumulatorKind,
    ConsistencyProof,
    ForkEvidenceReceipt,
    InclusionProof,
    InclusionVerdict,
    OrderingBasis,
    ReceiptEpochRoot,
    SequenceAuthority,
    operational_effect_of_inclusion,
    root_is_unsigned,
    timestamp_order_has_standing,
)

__all__ = [
    "FIREWALL",
    "NO_OPERATIONAL_EFFECT",
    "AccumulatorKind",
    "ConsistencyProof",
    "ForkEvidenceReceipt",
    "InclusionProof",
    "InclusionVerdict",
    "OrderingBasis",
    "ReceiptEpochRoot",
    "SequenceAuthority",
    "operational_effect_of_inclusion",
    "root_is_unsigned",
    "timestamp_order_has_standing",
]
