# SPDX-License-Identifier: Apache-2.0
"""Translation layer: StandingReceipt → receipt_kernel envelope.

Per ratified Q1 (Option A), standing-class receipts ride the
``libs/receipt_kernel`` ledger. This module is **pure translation**:
shape conversion only, no policy lookup, no admissibility logic, no
doctrine reinterpretation. All of those live in
:mod:`governor.standing.validator` and
:mod:`governor.standing.policy_registry`.

Working choice: payload-overload (Q1.A deferred). Standing-specific
fields ride in the ``payload`` of existing kernel event types. This
keeps ``EVENT_SCHEMA_VERSION`` stable and makes the future Q1.A
ratification of "new event types" an additive migration.
"""

from __future__ import annotations

from typing import Any

from receipt_kernel.envelope import make_envelope

from governor.standing.types import (
    StandingClass,
    StandingReceipt,
    ValidationReceipt,
)


# Standing class → kernel event_type. Values come from
# ``receipt_kernel.types.VALID_EVENT_TYPES``. Mappings are working
# choices documented in Q1's ratification basis (OBSERVE →
# EVIDENCE_PUT, AUTHORIZE → DECISION); the others are picked by
# analogy and may be re-pinned when Q1.A ratifies.
STANDING_TO_EVENT_TYPE: dict[StandingClass, str] = {
    StandingClass.OBSERVE: "EVIDENCE_PUT",
    StandingClass.INTERPRET: "EVALUATION",
    StandingClass.RECOMMEND: "EVALUATION",
    StandingClass.AUTHORIZE: "DECISION",
    StandingClass.EXECUTE: "REMEDIATION",
    StandingClass.POLICY_DECLARE: "DECISION",
}


def to_kernel_envelope(
    receipt: StandingReceipt,
    *,
    stage: str,
    policy_id: str,
    policy_version: str,
    stage_graph_id: str,
    actor_kind: str = "governor",
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Build a kernel envelope carrying a standing receipt in its payload.

    Caller fills ``stage`` and policy/actor fields. ``run_id``, ``seq``,
    ``prev_event_hash``, and ``event_hash`` are filled by the store on
    append (kernel contract).
    """

    event_type = STANDING_TO_EVENT_TYPE[receipt.standing_class]
    payload: dict[str, Any] = {
        "receipt_role": receipt.receipt_role.value,
        "standing_class": receipt.standing_class.value,
        "subject": receipt.subject,
        "ontology_version": receipt.ontology_version,
        "standing_receipt": receipt.canonical_body(),
        "standing_content_hash": receipt.compute_content_hash(),
    }
    return make_envelope(
        event_type=event_type,
        stage=stage,
        policy_id=policy_id,
        policy_version=policy_version,
        stage_graph_id=stage_graph_id,
        actor_kind=actor_kind,
        actor_id=actor_id or receipt.producer,
        payload=payload,
    )


def validation_to_kernel_envelope(
    validation: ValidationReceipt,
    *,
    stage: str,
    policy_id: str,
    policy_version: str,
    stage_graph_id: str,
    actor_kind: str = "governor",
) -> dict[str, Any]:
    """Build a kernel envelope carrying a validation receipt in its payload.

    Validation receipts are meta-governance (validator_contract §16).
    They ride EVALUATION events under Q1.A's payload-overload choice.
    """

    payload: dict[str, Any] = {
        "receipt_role": "validation",
        "validation_receipt": validation.to_dict(),
    }
    return make_envelope(
        event_type="EVALUATION",
        stage=stage,
        policy_id=policy_id,
        policy_version=policy_version,
        stage_graph_id=stage_graph_id,
        actor_kind=actor_kind,
        actor_id=validation.validator_id,
        payload=payload,
    )
