# PCAR-E: Actuator Contract and Execution Semantics
## Proof-Carrying Action at the Execution Boundary

- **Status:** Draft
- **Version:** 0.1.0
- **Family:** PCAR
- **Depends on:** PCAR-000, PCAR-A, PCAR-B, PCAR-C, PCAR-D
- **Last Updated:** 2026-02-23
- **Author(s):** [TBD]

---

## 1. Abstract

PCAR-E defines the **Action Contract** schema and **Actuator** validation semantics for a Proof-Carrying Agent Runtime (PCAR).

The actuator is the execution boundary. It is the last gate before the outside world changes. PCAR-E is intentionally dumb: it validates structured contracts against proof and decision requirements, executes if and only if all requirements are met, and emits receipts. It does not interpret, infer, improvise, or fall back.

The single most important property of PCAR-E is what it refuses to do: parse free text into action, guess intent from ambiguous input, or helpfully fill in missing parameters.

---

## 2. Scope

PCAR-E specifies:

- action contract schema,
- actuator validation sequence,
- execution result schema,
- action type registry (initial),
- scope enforcement model,
- idempotency and replay semantics,
- actuator-level error semantics.

PCAR-E does **not** specify:

- claim typing (PCAR-A),
- proof generation (PCAR-B),
- constraint evaluation (PCAR-C),
- receipt canonicalization (PCAR-D),
- replay artifact format (PCAR-R).

---

## 3. Design Goals

### 3.1 No Free-Text Actuation Path

The actuator MUST NOT accept natural language as an instruction. No parsing of prose into commands. No "I think you meant..." inference. No helpful fallback. If the action contract is not structured and valid, the action does not happen.

This is the NLAI invariant (PCAR-000 Section 8.1) at its most concrete.

### 3.2 No Execution on Expired State

The actuator MUST verify that the constraint decision authorizing the action has not expired and that the proof set is still fresh. Stale authorization is not authorization.

### 3.3 Mechanical Scope Enforcement

Scope is enforced mechanically, not by "intent." The actuator checks allowed paths, allowed verbs, allowed targets. If the action falls outside the declared scope, it is rejected regardless of how reasonable it seems.

### 3.4 All Outcomes Receipted

Every execution attempt — success, failure, rejection — MUST produce a receipt (PCAR-D). The actuator is the primary source of execution receipts.

### 3.5 Dumb on Purpose

Simplicity at the execution boundary is a feature, not a limitation. The actuator does not need to be smart. It needs to be correct and predictable. All intelligence belongs upstream (claims, proofs, decisions).

---

## 4. Normative Language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119 / RFC 8174.

---

## 5. Terminology

### 5.1 Action Contract
A structured request for the actuator to perform a specific action, carrying references to the authorizing decision and required proofs.

### 5.2 Actuator
A runtime component that validates action contracts and executes them if all requirements are satisfied. The actuator is the trust boundary between the PCAR runtime and the outside world.

### 5.3 Execution Result
A structured record of an action execution attempt, including outcome, side effects, and timing.

### 5.4 Action Type
A categorization of the action to be performed (e.g., file write, command execution, API call).

### 5.5 Nonce
A unique value associated with an action contract to prevent replay. Each contract MUST have a unique nonce within its scope.

---

## 6. Processing Model (PCAR-E)

### 6.1 Validation Sequence

The actuator MUST validate action contracts in this exact order. Validation is fail-fast: the first failure terminates validation and the action is rejected.

1. **Schema validation**: Action contract matches the required schema (Section 7).
2. **Decision exists**: Referenced `decision_id` resolves to a valid constraint decision (PCAR-C).
3. **Decision unexpired**: The constraint decision's `expires_at` has not passed.
4. **Decision authorizes**: The decision's `decision` field is `ALLOW`.
5. **Proof set present**: All `required_proof_ids` resolve to valid proof objects (PCAR-B).
6. **Proofs fresh**: All referenced proofs are within their freshness window.
7. **Proofs status-compatible**: All referenced proofs have status `PASS` (or as specified by policy for the action type).
8. **Scope valid**: The action's `target_scope` falls within the scope allowed by the decision's constraints.
9. **Nonce valid**: The nonce has not been previously used (no replay).
10. **Contract unexpired**: The action contract's `expires_at` has not passed.
11. **Constraints compatible**: Any constraints on the decision are compatible with the action (e.g., `read_only` + write action = reject).

If all 11 checks pass: **execute**.
If any check fails: **reject**, emit rejection receipt, stop.

### 6.2 Execution

After successful validation:
1. Record start time.
2. Execute the action.
3. Record end time.
4. Capture execution result (exit code, output hash, side effects).
5. Emit execution receipt (PCAR-D).

### 6.3 Post-Execution

After execution:
- The execution result MUST be available for downstream proof generation (e.g., PCAR-B `core.TOOL_RESULT`).
- The execution receipt MUST be emitted before or atomically with the result becoming available.

---

## 7. Action Contract Schema (Normative)

### 7.1 Required Fields

#### `action_request_id` (string)
Unique identifier for this action contract.

Requirements:
- MUST be unique within the current run/session scope.
- SHOULD be traceable to the originating PCAR-A `REQUESTED_ACTION` claim.

#### `action_type` (string)
The type of action to perform. See Section 9.

#### `target_scope` (object)
Where the action targets.

Required members:
- `scope_type` (string) — e.g., `filesystem`, `command`, `api`, `network`
- `scope_ref` (string) — specific target (path, command, URL)

Optional members:
- `allowed_roots` (array of strings) — explicitly allowed root paths/targets
- `denied_patterns` (array of strings) — explicitly denied patterns

#### `parameters` (object)
Action-type-specific parameters. Schema depends on `action_type` (Section 9).

#### `decision_id` (string)
Reference to the PCAR-C constraint decision authorizing this action.

#### `required_proof_ids` (array of strings)
References to PCAR-B proof objects required for this action.

#### `nonce` (string)
Unique value for replay prevention.

Requirements:
- MUST be unique per action contract within the session/run.
- SHOULD be a UUID or equivalent high-entropy identifier.

#### `requested_at` (timestamp)
When the action was requested. RFC 3339, UTC.

#### `expires_at` (timestamp)
When the action contract expires. RFC 3339, UTC.

An expired contract MUST NOT be executed. Default expiry SHOULD be short (e.g., 5 minutes).

### 7.2 Optional Fields

#### `idempotency_key` (string)
For idempotent actions, a key that identifies logical equivalence. Two contracts with the same idempotency key represent the same intended action.

#### `preconditions` (array)
Additional conditions that must hold at execution time.

Each precondition MUST include:
- `condition_type` (string) — e.g., `file_exists`, `process_not_running`, `port_available`
- `parameters` (object) — condition-specific parameters
- `required` (boolean) — whether failure blocks execution

#### `expected_effect` (string)
Human-readable description of the expected outcome. Non-authoritative — for logging and audit, not for execution logic.

#### `metadata` (object)
Implementation-specific metadata.

#### `extensions` (object)
Reserved for implementation-specific fields.

---

## 8. Execution Result Schema (Normative)

### 8.1 Required Fields

#### `result_status` (enum)
The outcome of the execution attempt.

Required values:
- `SUCCESS` — action completed as expected.
- `FAIL` — action failed during execution.
- `PARTIAL` — action partially completed (some side effects may have occurred).
- `REJECTED` — action was rejected during validation (not executed).

#### `action_request_id` (string)
Reference to the action contract.

#### `result_digest` (string)
Content hash of the execution output (stdout, response body, etc.).

If no output was produced, this SHOULD be the hash of an empty payload.

#### `started_at` (timestamp)
When execution began. RFC 3339, UTC. `null` if rejected before execution.

#### `ended_at` (timestamp)
When execution completed. RFC 3339, UTC. `null` if rejected before execution.

### 8.2 Optional Fields

#### `exit_code` (integer)
Process exit code, if applicable.

#### `side_effect_refs` (array)
References to side effects produced by the action.

Each entry MUST include:
- `effect_type` (string) — e.g., `file_created`, `file_modified`, `file_deleted`, `api_called`, `process_started`
- `effect_ref` (string) — specific reference (path, URL, PID)
- `effect_digest` (string, optional) — content hash of the affected artifact's new state

#### `output_refs` (object)
References to captured output.

Members:
- `stdout_ref` (string, optional) — evidence store reference for stdout
- `stderr_ref` (string, optional) — evidence store reference for stderr
- `response_ref` (string, optional) — evidence store reference for API response

#### `rejection_reason` (object)
Present only when `result_status` is `REJECTED`.

Required members:
- `validation_step` (integer) — which validation step failed (1-11, per Section 6.1)
- `error_code` (string) — PCAR-E error code
- `message` (string) — human-readable explanation

#### `metadata` (object)
Implementation-specific metadata.

---

## 9. Action Type Registry (Normative)

### 9.1 Core Action Types

Implementations MUST support these action types:

#### `command_exec`
Execute a shell command.

Parameters:
- `argv` (array of strings) — command and arguments
- `cwd` (string, optional) — working directory
- `env` (object, optional) — environment variables
- `timeout_seconds` (integer, optional) — execution timeout

#### `file_read`
Read a file's contents.

Parameters:
- `path` (string) — file path
- `encoding` (string, optional) — character encoding

#### `file_write`
Write or modify a file.

Parameters:
- `path` (string) — file path
- `content` (string) — file content or patch
- `mode` (string) — `create`, `overwrite`, `append`, `patch`
- `encoding` (string, optional) — character encoding

#### `api_call`
Make an API request.

Parameters:
- `method` (string) — HTTP method
- `url` (string) — target URL
- `headers` (object, optional) — request headers
- `body` (string | object, optional) — request body
- `timeout_seconds` (integer, optional) — request timeout

#### `patch_apply`
Apply a structured diff/patch.

Parameters:
- `patch_content` (string) — the patch
- `patch_format` (string) — `unified_diff`, `json_patch`, `custom`
- `target_path` (string) — file to patch

#### `test_run`
Execute a test suite.

Parameters:
- `command` (array of strings) — test runner command
- `cwd` (string, optional) — working directory
- `timeout_seconds` (integer, optional) — execution timeout

### 9.2 Action Type Registration

Implementations MAY define additional action types. Custom action types:
- MUST include a parameter schema.
- MUST include scope requirements.
- SHOULD be namespaced (e.g., `vendor.custom_action`).
- MUST NOT redefine core action types.

---

## 10. Scope Enforcement (Normative)

### 10.1 Scope Model

Scope enforcement is mechanical. The actuator checks that the action's target falls within allowed bounds. There is no inference, no "probably meant," no helpful expansion.

### 10.2 Scope Dimensions

| Dimension | Check |
|-----------|-------|
| **Paths** | Target path must fall within allowed roots. No traversal outside declared scope. |
| **Verbs** | Action type must be in allowed set. `read_only` constraint blocks writes. |
| **Network** | Target URLs/hosts must be in allowlist (if network constraints active). |
| **Processes** | Spawned processes must be in allowed command set. |

### 10.3 Path Enforcement Rules

- Paths MUST be normalized (resolved symlinks, no `..` traversal outside scope).
- Allowed roots define the maximum extent. Anything outside is denied.
- Denied patterns override allowed roots (deny takes precedence).
- If no allowed roots are specified, the action targets MUST fall within the decision's scope.

### 10.4 No Implicit Scope Expansion

The actuator MUST NOT:
- expand wildcards beyond declared scope,
- follow symlinks outside scope,
- normalize paths in a way that escapes scope boundaries,
- interpret "implicit" or "obvious" scope from context.

If the scope is insufficient for the action, the action is rejected. The solution is to request a broader scope upstream (PCAR-A → PCAR-C), not to stretch the actuator's scope.

---

## 11. Idempotency and Replay (Normative)

### 11.1 Nonce Uniqueness

Each action contract MUST include a unique `nonce`. The actuator MUST reject contracts with previously-used nonces.

Nonce tracking:
- Nonces MUST be tracked for at least the duration of the session/run.
- Nonces MAY be tracked across sessions (implementation-defined).
- Nonce storage SHOULD survive actuator restart within a session.

### 11.2 Idempotent Actions

Actions with an `idempotency_key` may be retried safely. The actuator:
- MUST check the idempotency key against recent results.
- If a result exists for the same key: return the existing result, do not re-execute.
- If no result exists: execute normally and record the result keyed by idempotency_key.

### 11.3 Retry Semantics

PCAR-E does not specify automatic retry. If an action fails:
- The failure is receipted.
- A new action contract (with a new nonce) may be submitted.
- The new contract undergoes full validation (decision may have expired).

Automatic retry would bypass the validation sequence and is NOT PCAR-E conformant.

### 11.4 Exactly-Once vs At-Least-Once

PCAR-E targets **at-most-once** execution semantics:
- An action is executed zero times (if rejected) or one time (if validated).
- Partial execution (`PARTIAL` result) means some side effects occurred.
- Exactly-once is not guaranteed in the presence of crashes between execution and receipt emission.

For actions requiring stronger guarantees, use `idempotency_key` to enable safe retry.

---

## 12. Forbidden Patterns (Normative)

The following patterns are explicitly forbidden in PCAR-E implementations:

### 12.1 Helpful Fallback Parsing

```
# FORBIDDEN
if not valid_action_contract(contract):
    guess = parse_intent_from_text(contract.metadata.description)
    execute(guess)
```

If the contract is not valid, the action does not happen. There is no "best effort" at the execution boundary. This is a jailbreak tunnel.

### 12.2 Implicit Authorization

```
# FORBIDDEN
if action_seems_safe(contract):
    skip_decision_check()
    execute(contract)
```

All actions require an authorizing decision. "Seems safe" is not a decision.

### 12.3 Scope Inference

```
# FORBIDDEN
if contract.target_scope is None:
    infer_scope_from_action_type(contract)
```

Missing scope is a rejection, not an inference opportunity.

### 12.4 Silent Retry

```
# FORBIDDEN
while not success:
    try: execute(contract)
    except: continue
```

Failed actions are receipted and returned. Retry requires a new contract through the full pipeline.

### 12.5 Decision Extension

```
# FORBIDDEN
if decision.expired and decision.was_allow:
    extend_decision(decision, minutes=5)
    execute(contract)
```

Expired decisions are dead. A new decision is required.

---

## 13. Error Model (Normative)

### 13.1 Error Object Shape

Each error MUST include:
- `error_code`
- `severity` (`ERROR`, `WARN`)
- `message`
- `action_request_id` (if applicable)
- `validation_step` (integer, if validation failure)

### 13.2 Required Error Codes

#### Contract Validation
- `PCAR_E_CONTRACT_INVALID` — action contract fails schema validation
- `PCAR_E_CONTRACT_EXPIRED` — action contract has expired
- `PCAR_E_MISSING_DECISION` — referenced decision not found
- `PCAR_E_DECISION_EXPIRED` — referenced decision has expired
- `PCAR_E_DECISION_NOT_ALLOW` — decision is not ALLOW

#### Proof Validation
- `PCAR_E_PROOF_SET_INVALID` — required proofs not all present or valid
- `PCAR_E_PROOF_STALE` — referenced proof has expired
- `PCAR_E_PROOF_STATUS_INCOMPATIBLE` — proof status does not meet requirements

#### Scope
- `PCAR_E_SCOPE_VIOLATION` — action target outside allowed scope
- `PCAR_E_SCOPE_MISSING` — action contract lacks target scope

#### Replay Prevention
- `PCAR_E_NONCE_REUSE` — nonce has been previously used
- `PCAR_E_NONCE_MISSING` — action contract lacks nonce

#### Execution
- `PCAR_E_EXECUTION_FAILURE` — action failed during execution
- `PCAR_E_EXECUTION_TIMEOUT` — action exceeded timeout
- `PCAR_E_PARTIAL_EXECUTION` — action partially completed

#### Constraint
- `PCAR_E_CONSTRAINT_VIOLATION` — action incompatible with decision constraints

### 13.3 Error Handling Rules

- Validation failures produce `REJECTED` results with the failing step identified.
- Execution failures produce `FAIL` or `PARTIAL` results with captured output.
- All errors are receipted.
- The actuator MUST NOT produce "helpful" suggestions for fixing validation failures — that intelligence belongs upstream.

---

## 14. Security Considerations (PCAR-E Specific)

### 14.1 Command Injection

Action parameters (especially `command_exec`) are high-risk for injection. Mitigations:
- Commands MUST be passed as structured `argv` arrays, not shell strings.
- The actuator MUST NOT invoke a shell to interpret commands.
- Environment variables MUST be explicitly declared, not inherited wholesale.

### 14.2 Path Traversal

File operations may attempt path traversal. Mitigations:
- All paths MUST be normalized before scope checking.
- Symlinks MUST be resolved before scope checking.
- `..` components that escape scope MUST be rejected.

### 14.3 Time-of-Check-Time-of-Use (TOCTOU)

Between validation and execution, state may change. Mitigations:
- Validation and execution SHOULD be atomic where possible.
- Execution results capture the actual state at execution time.
- Post-execution verification (via PCAR-B) detects state drift.

### 14.4 Side Effect Leakage

Even rejected or failed actions may have produced side effects (partial writes, network connections). Mitigations:
- `PARTIAL` results MUST declare observed side effects.
- Side effect cleanup is implementation-defined but MUST be receipted.

### 14.5 Nonce Exhaustion

An attacker may try to exhaust the nonce tracking store. Mitigations:
- Nonce stores SHOULD have bounded size with LRU eviction.
- Evicted nonces SHOULD be logged.
- Actions with very old nonces SHOULD be rejected by contract expiry before nonce check.

---

## 15. Privacy Considerations (PCAR-E Specific)

Action parameters and execution results may contain sensitive data. Implementations SHOULD support:

- parameter redaction in exported receipts,
- output redaction with digest preservation,
- scoped access to execution results.

Redaction MUST NOT break receipt integrity or execution result digests.

---

## 16. Conformance

An implementation is **PCAR-E conformant** if it:

1. Validates action contracts in the order specified in Section 6.1.
2. Produces execution results matching Section 8.
3. Supports all core action types in Section 9.1.
4. Enforces scope mechanically per Section 10.
5. Prevents replay via nonce tracking per Section 11.
6. Does not accept free-text actuation paths (Section 12.1).
7. Does not execute on expired decisions or proofs.
8. Emits receipts for all execution outcomes.
9. Emits machine-readable errors per Section 13.

---

## 17. Informative Examples

### 17.1 Example: Successful Command Execution

```json
{
  "action_request_id": "act-001",
  "action_type": "command_exec",
  "target_scope": {
    "scope_type": "command",
    "scope_ref": "pytest",
    "allowed_roots": ["/workspace/agent_gov"]
  },
  "parameters": {
    "argv": ["pytest", "-q", "tests/"],
    "cwd": "/workspace/agent_gov",
    "timeout_seconds": 120
  },
  "decision_id": "d-001",
  "required_proof_ids": ["p-001", "p-003"],
  "nonce": "550e8400-e29b-41d4-a716-446655440000",
  "requested_at": "2026-02-23T15:00:00Z",
  "expires_at": "2026-02-23T15:05:00Z"
}
```

Result:

```json
{
  "result_status": "SUCCESS",
  "action_request_id": "act-001",
  "result_digest": "sha256:test_output_hash...",
  "exit_code": 0,
  "started_at": "2026-02-23T15:00:01Z",
  "ended_at": "2026-02-23T15:00:45Z",
  "output_refs": {
    "stdout_ref": "blob:sha256:stdout_hash...",
    "stderr_ref": "blob:sha256:stderr_hash..."
  }
}
```

### 17.2 Example: Rejected Action (Scope Violation)

```json
{
  "result_status": "REJECTED",
  "action_request_id": "act-002",
  "result_digest": "sha256:empty...",
  "started_at": null,
  "ended_at": null,
  "rejection_reason": {
    "validation_step": 8,
    "error_code": "PCAR_E_SCOPE_VIOLATION",
    "message": "Target path /etc/passwd outside allowed roots [/workspace/agent_gov]"
  }
}
```

### 17.3 Example: Rejected Action (Expired Decision)

```json
{
  "result_status": "REJECTED",
  "action_request_id": "act-003",
  "result_digest": "sha256:empty...",
  "started_at": null,
  "ended_at": null,
  "rejection_reason": {
    "validation_step": 3,
    "error_code": "PCAR_E_DECISION_EXPIRED",
    "message": "Decision d-001 expired at 2026-02-23T15:05:00Z, current time 2026-02-23T15:07:00Z"
  }
}
```

---

## 18. Open Questions

- Should the actuator support "dry run" mode (validate but don't execute)?
- Should `PARTIAL` execution results include a rollback hint?
- How should the actuator handle actions that produce non-deterministic output (e.g., timestamps in tool output)?
- Should nonce tracking be centralized (daemon-level) or per-actuator?
- What is the maximum acceptable latency between validation and execution before state drift becomes a concern?

---

## 19. References (Informative)

- PCAR-000: Proof-Carrying Agent Runtime
- PCAR-A: Typed Claim Envelope
- PCAR-B: Proof Objects and Verifier Contract
- PCAR-C: Constraint Decisions and Regime Derivation
- PCAR-D: Receipt Canonicalization and Provenance Contract
- RFC 2119
- RFC 8174
