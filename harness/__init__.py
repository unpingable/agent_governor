# SPDX-License-Identifier: Apache-2.0
"""H-series external actor harness (OUTSIDE AG).

This package is **not** part of the governor runtime. It is the foreign producer
that, in the synthetic conveyor, runs an offline actor and captures what it said
into an inert ``actor_output.v0`` JSON artifact. AG then *ingests* that JSON.

Boundary rule (load-bearing — see ``harness/README.md``):

    H1 may run the actor; AG may only ingest the captured artifact.

Hard invariants (enforced by AG-side contract tests, ``tests/harness/``):

- Nothing under ``harness/`` imports ``governor`` (or S5/S7/ration-card/admission/
  validator internals). The contract is the JSON envelope, not shared Python types.
- It produces ONLY ``actor_output.v0`` testimony — never a verified test result,
  verifier receipt, admission receipt, or anything that can green S5.
  ``claimed_test_results`` stay *claims*.

The public surface lives in ``harness.actor_harness`` (kept out of this ``__init__``
so ``python -m harness.actor_harness`` runs without an import-order warning).
"""
