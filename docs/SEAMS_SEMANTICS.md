# Seams Semantics (2.x → 3.x)

Additive fields laid as seams for 3.x architecture. Schema version bumped to **3**
(`receipt_role` changes receipt identity — same payload, different role = different receipt_id).

## `receipt_role` (on GateReceipt)

Included in `receipt_id` hash — different role = different receipt.

| Value | Meaning |
|-------|---------|
| `measurement` | Default. Observational gate output (evidence check, continuity). |
| `proposal` | Intent compilation, plan submission. |
| `authority` | Binding governance decision (pre-commit block, scope denial). |
| `recovery_plan` | Remediation artifact submitted for review. |
| `reset` | System state mutation request (emitted pre-mutation). |

## `independence_class` (on EvidenceRef)

Provenance independence for correlation analysis.

| Value | Meaning |
|-------|---------|
| `self` | Evidence produced by the same agent making the claim. |
| `tool` | Evidence from a deterministic tool (pytest, linter, hash). |
| `peer` | Evidence from a different agent in the same system. |
| `external` | Evidence from an external source (URL, API, database). |
| `operator` | Evidence from a human operator. |
| `unknown` | Classification not yet determined. Analytics bucket, not None. |

## `system_reset_request`

Emitted **before** state mutation. Records intent, **not** completion.
Do not treat as proof that the reset succeeded. A future `system_reset_complete`
event may follow in 3.x.

## `ActionClass` (in `regime.py`)

Policy seam — what kind of action is being attempted.

| Value | Meaning |
|-------|---------|
| `read` | Read-only access to state or files. |
| `write` | Mutation of files or persistent state. |
| `execute` | Running commands, subprocesses, tools. |
| `configure` | Changing settings, thresholds, profiles. |
| `reset` | Clearing subsystem state. |
| `status` | Querying current status (always allowed). |
| `recovery_submit` | Submitting a recovery plan for review. |

## `DenyReason` (in `regime.py`)

Audit semantics — why an action was denied.

| Value | Meaning |
|-------|---------|
| `regime_restricted` | Current operational regime forbids this action class. |
| `locked_route` | LOCKED routing prevents this action (3.x seam). |
| `stale_snapshot` | Action based on outdated state. |
| `budget_exhausted` | Resource budget consumed. |
| `scope_violation` | Action outside granted scope. |
| `capture_detected` | Correlator flagged capture condition. |

## `ResetReason` (in `regime.py`)

Why a reset was initiated.

| Value | Meaning |
|-------|---------|
| `operator_request` | Human operator requested reset. |
| `recovery_failure` | Automated recovery failed, fallback to reset. |
| `regime_transition` | Reset triggered by regime change. |
| `manual_cli` | Reset via CLI command (default for `governor X reset`). |
| `scheduled` | Periodic/scheduled maintenance reset. |

## Reason code stability

All enum values above are **append-only**.
Values are never renamed or removed. New values may be added in any release.

## Enum home directory

| Enum | Home module | Used by |
|------|-------------|---------|
| `receipt_role` constants | `gate_receipt.py` | All gates, CLI reset helper |
| `ActionClass` | `regime.py` | `check_regime_allows()`, future routing |
| `DenyReason` | `regime.py` | `check_regime_allows()`, future audit trail |
| `ResetReason` | `regime.py` | CLI `_emit_reset_receipt()` evidence |
| `INDEPENDENCE_CLASSES` | `epistemic.py` | `EvidenceRef` validation, factory defaults |
