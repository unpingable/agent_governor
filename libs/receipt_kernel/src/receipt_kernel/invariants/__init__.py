"""Constitutional invariants for the receipt kernel.

Six invariants that together ensure:
- The ledger is tamper-evident (chain_valid)
- Evidence is complete and retrievable (receipt_completeness)
- Evaluations are attested and non-downgrading (evaluation_completeness)
- Runs end cleanly (finalization_completeness)
- Runs end exactly once (single_finalize)
- Runs follow required stage paths (stage_required_path)
"""

from receipt_kernel.invariants.ledger_chain_valid import LedgerChainValidInvariant
from receipt_kernel.invariants.receipt_completeness import ReceiptCompletenessInvariant
from receipt_kernel.invariants.evaluation_completeness import EvaluationCompletenessInvariant
from receipt_kernel.invariants.finalization_completeness import FinalizationCompletenessInvariant
from receipt_kernel.invariants.run_shape import SingleFinalizeInvariant, StageRequiredPathInvariant

__all__ = [
    "LedgerChainValidInvariant",
    "ReceiptCompletenessInvariant",
    "EvaluationCompletenessInvariant",
    "FinalizationCompletenessInvariant",
    "SingleFinalizeInvariant",
    "StageRequiredPathInvariant",
]
