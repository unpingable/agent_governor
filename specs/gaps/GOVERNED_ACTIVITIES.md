# Governed Activities

Receipted side-effect capsules for workflow orchestration. Deterministic
orchestration calls non-deterministic actions through a governed gate.

status: gap spec (v2.x foundation + v3 extensions, v2 types implemented)

---

## Problem

Workflow orchestrators (Temporal, Step Functions, etc.) retry activities
blindly. Retries are reflexive, not governed:

- Preconditions aren't re-validated between attempts
- "Success" is assumed if the call returns 200, not verified
- Retries can amplify stale assumptions ("repeat the lie faster")
- No portable evidence of what happened, why it was allowed, what changed

Governor already has the primitives for governed side-effects (receipts,
chain gate, CAS binding, policy hashing). What's missing is the contract
shape for *workflow-orchestrated* actions with retry semantics.

---

## Terminology Mapping

| Workflow concept | Governor equivalent | Notes |
|-----------------|---------------------|-------|
| `call_id` (stable per logical step) | `record_id` in chain_gate | Exists |
| `policy_bundle_id` (pinned) | `policy_hash` in gate receipts | Exists |
| `idempotency_key` | CAS binding token in chain_gate | Exists |
| Pre/postcondition facts | Evidence gate + oracle evidence | Exists (single-run) |
| Receipt fragment (hash-chained) | GateReceipt + receipt kernel | Exists |
| "Don't fabricate facts" | NLAI invariant | Core principle |
| FactObservation (freshness + etag) | TTL enforcement + fact decay | Different shape — **new** |
| Retry gated by precondition drift | No equivalent | **New** |
| `carried_facts` (workflow→activity) | No equivalent | **v3 only, suspicious** |

### Two Orthogonal Axes

Do not collapse these:

- **Verdict** = what the gate decided (pass / warn / block / observe / proceed)
- **Outcome** = what happened (success / business_failure / system_failure)

These are independent. "Allowed, but business failure" (quota exceeded) is
different from "denied, but system healthy" (policy block). Forcing a 1:1
mapping loses information.

---

## What's Genuinely New

### 1. Drift-Gated Retries

Temporal retries are blind. Governed retries re-validate preconditions:

**Algorithm:**

```
on_attempt(call_id, attempt_n, args):
  1. Gather precondition facts → compute precondition_fingerprint
  2. If attempt_n > 1:
     a. Fetch previous attempt's precondition_fingerprint
     b. If changed → STOP:
        outcome = business_failure
        error.class = DivergenceDetected
        retry_class = unsafe
     c. If unchanged → proceed (retry is safe_transient)
  3. Execute side-effect with stable idempotency_key
  4. Gather postcondition facts
  5. Verify postconditions match declared invariants
  6. Emit receipt with pre/post fingerprints
  7. Return result envelope
```

**Precondition fingerprint:**

```
precondition_fingerprint = H(canonical(precondition_bundle))
```

Where `precondition_bundle` is a list of FactObservations (or just
concurrency tokens + bounds). Stored in the attempt receipt under
`(call_id, attempt)`.

**What this kills:** retry storms that amplify stale state. If the ASG
changed between attempts, the retry is operating on a different world
than the original intent. Stop and escalate, don't keep hammering.

### 2. FactObservation (ops-native fact type)

Governor "facts" today are ledger-ish (file exists, tests pass). This
is a different subtype: "I observed external system state at time t."

```
FactObservation:
  fact_type:              str    # "DescribeAutoScalingGroup"
  subject:                str?   # "asg/my-service-prod"
  observed_at:            str    # ISO 8601 UTC
  request_fingerprint:    str?   # H(request params)
  response_fingerprint:   str?   # H(response summary)
  etag_or_version:        str?   # concurrency token from provider
  freshness_s:            int?   # validity window in seconds
  confidence:             str?   # "low" | "med" | "high"
  source:                 str?   # "AWS", "k8s", "internal-db"
```

Key properties:
- **Freshness**: fact is only valid for N seconds (not indefinitely)
- **Concurrency token**: ties observation to a specific version of reality
- **Fingerprints**: diffable without storing secrets
- **Source attribution**: which external system was queried

This is the ops-governor's natural evolution. Not more metaphysics —
"did the ASG change under us."

---

## Activity Envelope Shape

Single-argument, evolvable, governance-ready.

```
ActivityEnvelope<I>:
  schema_id:              "gov.activity_envelope.v1"

  header:
    workflow_id:          str     # orchestrator workflow ID
    run_id:               str     # orchestrator run ID
    activity_type:        str     # "ResizeServerGroup"
    call_id:              str     # stable per logical step (NOT per attempt)
    attempt:              int     # attempt count (1..n)
    policy_bundle_id:     str     # content-addressed policy hash
    invariant_set_id:     str?    # optional now, mandatory v3
    risk_regime:          str?    # "low" | "med" | "high"

  input:
    input_schema:         str     # "ResizeServerGroupInput@v3"
    value:                I
    value_hash:           str?    # H(canonical(value_redacted))
    redaction_profile:    str?

  constraints:
    require_idempotency:  bool
    require_preconditions: list[str]?   # ["asg_version_matches"]
    require_postconditions: list[str]?  # ["desired_capacity_set"]
    max_wallclock_s:      int?
```

```
ActivityResultEnvelope<O>:
  schema_id:              "gov.activity_result.v1"

  header:
    workflow_id:          str
    run_id:               str
    call_id:              str
    attempt:              int
    receipt_hash:         str     # H(receipt_fragment)

  status:
    outcome:              "success" | "business_failure" | "system_failure"
    retry_class:          "none" | "safe_transient" | "unsafe" | "unknown"

  output:
    output_schema:        str?
    value:                O?
    value_hash:           str?

  error:
    class:                str?    # "DivergenceDetected" | "QuotaExceeded" | ...
    message:              str?    # short, scrubbed
    details_hash:         str?

  evidence:
    pre_facts:            list[FactObservation]?
    post_facts:           list[FactObservation]?
    verified_invariants:  list[str]?
    violated_invariants:  list[str]?
```

---

## v2 vs v3 Split

### v2 foundation (small, no regret)

- `precondition_fingerprint` field on attempt receipts
- `retry_class` field on result envelope
- `DivergenceDetected` as standard business-failure class
- Drift-gate check in the activity runner (not in workflows)
- `FactObservation` type (ops-native facts with freshness + tokens)

No new engine. Just: receipts + a lookup + a rule.

### v3 extensions (requires more design)

- Full `ActivityEnvelope` / `ActivityResultEnvelope` typed contracts
- `invariant_set_id` pinning with evolution discipline
- Postcondition verification in the wrapper
- Policy/invariant set pinning + schema evolution
- `carried_facts` from workflows to activities (if ever — see non-goals)

---

## Non-Goals

- **No workflow-carried facts.** Workflows must not hand activities "facts."
  They may pass fact *references* or *constraints* ("you must observe an
  ASG state fresher than 30s"). Activities perform observations themselves
  and receipt them. Otherwise NLAI is violated through a side door.

- **No cross-run global truth store.** FactObservations are per-attempt,
  per-activity. They don't accumulate into a shared world model.

- **No Temporal-specific coupling.** The contract works with any workflow
  orchestrator. Temporal is the motivating example, not a dependency.

- **No verdict↔outcome collapse.** These remain orthogonal axes.

---

## Canonicalization Rules (normative, v2)

### String normalization

All optional string fields in `fingerprint_dict()` normalize to `""`, never
`None`. Fields always present in fingerprint dict:

- `fact_type`, `subject`, `source`, `request_fingerprint`,
  `response_fingerprint`, `etag_or_version`

### Fields excluded from fingerprint

- `observed_at` — volatile timestamp
- `confidence` — advisory
- `freshness_s` — policy TTL, not world state

### Fields included in fingerprint (world state)

- `fact_type`, `subject`, `source`, `request_fingerprint`,
  `response_fingerprint`, `etag_or_version`

### Serialization

Reuses `canonical_json()` from `gate_receipt.py`: UTF-8, `ensure_ascii=True`,
sorted keys, compact separators. `ensure_ascii=True` sidesteps NFC/NFD Unicode
normalization issues by escaping all non-ASCII. No floats. All fingerprint
fields always present (never dropped).

**Unicode normalization stance:** `ensure_ascii=True` makes fingerprints
byte-stable across platforms but does NOT normalize visually-identical Unicode
(e.g., `e + combining-accent` vs `precomposed-e`). Machine-generated
identifiers (etags, hashes) are unaffected. Callers producing fingerprint
input from human-authored text should NFC-normalize before construction if
visual equivalence matters.

### `response_fingerprint` stability contract

The drift gate assumes `response_fingerprint` is semantically stable across
observations of the same logical state. It must be computed from a canonical
subset of the provider response — sorted keys, deterministic serialization,
non-deterministic fields (request IDs, timestamps, unordered collections)
excluded before hashing. False drift from unstable `response_fingerprint` is
a caller bug, not a gate bug.

### Sort order

`(fact_type, subject, request_fingerprint, response_fingerprint,
etag_or_version, source)` — all normalized to `""` for sort comparison.

---

## Tiered Drift Detection (v2 decision)

Resolves Open Question 1. Neither token-only nor fingerprint-only — tiered:

### Etag key

`f"{fact_type}:{subject or ''}:{source or ''}"` — includes source so the same
subject observed from two different providers doesn't collide.

**Why `request_fingerprint` is excluded from etag key:** etag_or_version is a
provider-assigned concurrency token for a *resource*, not a *query*. If the
same resource returns different etags depending on request parameters (filters,
regions, credentials), the caller should encode that distinction into `subject`
or `source` — not silently overload the same etag key. Including
request_fingerprint would split one provider token across multiple keys,
defeating the "did the resource change?" question etags answer.

### Decision tree

1. **Compute overlap**: `prior_etag_keys ∩ current_etag_keys`
2. **If overlap non-empty**:
   - Any overlapping token differs → `ETAG_DIVERGED` (retry_class = unsafe)
   - All match → fall through to fingerprint
3. **If prior had etags but current doesn't** (or vice versa) →
   `CONTINUITY_LOST` (retry_class = operator_required). Loss of tracking
   signal is not "no overlap" — it's a continuity break.
4. **If neither has etags**: fall through to fingerprint
5. **Fingerprint comparison**:
   - Match → `NO_DRIFT` (safe_transient)
   - Mismatch → `FINGERPRINT_DIVERGED` (unsafe)

### `operator_required` retry class

New classification for ambiguous situations:

| Error pattern | retry_class |
|---------------|-------------|
| Timeout after write | operator_required |
| Network error / throttle | safe_transient |
| Validation / quota / conflict | none (business_failure, don't retry) |
| Unknown / unclassified | unknown |
| Precondition diverged | unsafe |
| Continuity lost (etag tracking gap) | operator_required |

### Receipt emission observability

`DriftCheckResult` and `AttemptRecord` carry `receipt_emission_ok` (bool) and
`receipt_emission_error` (str). Drift verdict remains authoritative regardless,
but "auditing died" is never silent.

### AttemptStore performance

All queries do full JSONL scan — O(n) in total records. Acceptable for v2
foundation (not wired to production paths). Production wiring requires an
index or in-memory cache to avoid linear scans.

---

## Open Questions

1. ~~**How strict is drift detection?**~~ **RESOLVED in v2:** Tiered —
   etag overlap first, fingerprint fallback. See "Tiered Drift Detection."

2. **Override semantics.** When divergence is detected, can the operator
   force a retry? If so, that's a receipted override (existing pattern).

3. **Fingerprint redaction.** Precondition fingerprints may contain
   sensitive infrastructure state. Redaction profile needed.

4. **Postcondition verification scope.** How much verification is the
   activity runner responsible for vs the workflow? The wrapper algorithm
   says "activity verifies," but complex postconditions might need
   orchestrator-level checks.

5. **Integration surface.** Does this wire through the daemon? Through
   the chain gate? Through a new ops-governor subsystem? The chain gate's
   preflight/record split is the closest existing pattern.

---

## Relationship to Existing Specs

| Spec | Connection |
|------|-----------|
| Chain gate (2.3.2) | Preflight/record split, CAS binding, `record_id` = `call_id` |
| Gate receipts | Receipt fragment shape, content-addressed, hash-chained |
| Policy engine | `policy_bundle_id` pinning, risk regime classification |
| Ops governor | Natural home for FactObservation and ops-native fact types |
| TTL enforcement | Freshness semantics on FactObservation |
| Evidence gate | Pre/postcondition verification pattern |
| GOVERNANCE_ABUSE_AUDIT | Retry-as-governed-decision prevents P8 (compliance theater retries) |
| RELATIONAL_INVARIANTS | R1 (decision accountability) applies: every activity outcome must have a justifying evidence trace |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-26 | Initial gap spec. Drift-gated retries, FactObservation, envelope shapes, v2/v3 split. |
| 0.2 | 2026-02-26 | v2 foundation implemented: canonicalization rules, tiered drift (etag→fingerprint), `operator_required` retry class, `continuity_lost` verdict, JSONL AttemptStore. Resolved Open Question 1. Module: `src/governor/governed_activity.py`. |
