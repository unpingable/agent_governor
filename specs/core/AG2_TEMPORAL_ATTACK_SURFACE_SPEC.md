# Temporal Attack Surface Specification

## Version 0.1 — Δt-Aware Security Analysis

```yaml
status: gap
implemented: false
depends_on: [security.py, KERNEL_CONSTRAINTS_SPEC.md]
blocking: temporal vulnerability detection
estimated_scope: large
```

### Companion to: CODE_SRE_CONTROLLER_SPEC.md, MCP_SAFETY_SPEC.md

---

## Executive Summary

The governor's security scanner detects static vulnerability patterns (injection, secrets, XSS). It does not detect **temporal** vulnerability patterns — race windows, fail-open defaults, commitment polarity errors, and detection-response gaps.

The Temporal Attack Surface framework (Beck 2025, see `ingest/temporal_attack_surface.md`) formalizes these as control-theoretic race conditions. This spec defines how the governor can detect, instrument, and gate on temporal security properties in code.

**Core insight**: Security failures in asynchronous systems are race conditions, not configuration errors. The governor already enforces "language is a proposal, not an authority" — temporal analysis extends this to "timing is an assumption, not a guarantee."

---

## 1. The Problem

### 1.1 What the Security Scanner Catches Today

Static patterns:
- SQL injection (`f"SELECT * FROM {user_input}"`)
- Command injection (`subprocess.run(f"echo {user_input}", shell=True)`)
- Hardcoded secrets (`API_KEY = "sk-..."`)
- Path traversal, XSS, insecure deserialization

### 1.2 What It Misses

Temporal patterns:
- **TOCTOU races**: Check-then-act without atomicity (`if not exists: create`)
- **Fail-open defaults**: Timeout handlers that allow instead of deny
- **Commitment polarity errors**: Irreversible actions before verification completes
- **Detection-response gaps**: Logging without enforcement (`logger.warning(...)` then continue)
- **Human latency assumptions**: Approval flows that degrade under queue pressure

These are the patterns from the Δt framework's five security domains (SIEM, CI/CD, auth, rate limiting, human-in-loop), expressed as code-level antipatterns.

---

## 2. Temporal Risk Markers

Extend the existing 19 code interferometry risk markers with temporal markers.

### 2.1 Proposed Marker Types

| Marker | Pattern | Δt Concept |
|--------|---------|------------|
| `TOCTOU_RACE` | Check-then-act without lock/transaction | Race window: T_check < T_act |
| `FAIL_OPEN_DEFAULT` | Timeout/except handler that allows action | C_j = fail-open under uncertainty |
| `COMMIT_BEFORE_VERIFY` | Irreversible action before validation completes | T_commit < T_verify |
| `LOG_NOT_GATE` | Security violation logged but not blocked | A_j = ∞ (no enforcement) |
| `UNBOUNDED_RETRY` | Retry loop without backoff/limit | W_j inflation attack surface |
| `APPROVAL_NO_CONTEXT` | Human approval with insufficient info | κ_j exhaustion (rubber-stamp risk) |
| `ASYNC_ENFORCEMENT` | Detection and response in different processes/threads | W_j + A_j gap |
| `LONG_LIVED_CREDENTIAL` | Token/session with no expiry or long TTL | Large T_commit window |
| `BURST_CAPACITY` | Rate limiter with large bucket/no burst limit | Single-burst objective completion |

### 2.2 Scanner Patterns

The scanner flags code that **creates** failure domains, not just code that has bugs. The difference: "this SQL is injectable" vs "this architecture will fail under time pressure." The second is what nobody else catches.

Grepable antipatterns:

| Pattern | What It Catches | Why It's Temporal |
|---------|-----------------|-------------------|
| Waits without timeouts | Unbounded W_j | Race window is infinite |
| Retries without limits/backoff | Evidence erasure | E(t) gets lost in retry noise |
| "Warn and continue" | Fail-open C_j | Commitment despite failed verification |
| Irreversible before check | T_commit < T_verify | The core temporal failure |
| Async checks that don't gate | Decoupled evidence | Verification exists but doesn't govern |
| Manual-only response | Human W_j bottleneck | Fatigue domain |

Static analysis examples (same approach as existing security scanner):

```python
# TOCTOU_RACE: check-then-act without atomicity
if os.path.exists(path):        # T_check
    with open(path, 'w') as f:  # T_act (gap between check and act)

# FAIL_OPEN_DEFAULT: timeout allows action
try:
    verify(token)
except TimeoutError:
    allow()  # C_j = fail-open

# COMMIT_BEFORE_VERIFY: irreversible before validation
deploy(artifact)        # T_commit (irreversible)
scan_result = sast(artifact)  # T_verify (too late)

# LOG_NOT_GATE: advisory, not enforcement
if not governor.approve(patch):
    logger.warning("rejected")
    apply_patch(patch)  # No gate — A_j = ∞

# UNBOUNDED_RETRY: retries erase evidence
while True:
    try:
        result = call_api()
    except:
        continue  # No backoff, no limit, no evidence trail

# ASYNC_ENFORCEMENT: check result never gates anything
background_task(verify_signature, artifact)  # Fire and forget
deploy(artifact)  # Proceeds regardless of verification
```

---

## 3. Failure Domains

The W / E(t) / C structure generalizes across security domains. Each domain produces the same temporal failure signatures; the scanner catches code that creates these domains.

### 3.1 Core Five (from paper)

| Domain | W_j | E(t) | C_j | Failure Signature |
|--------|-----|------|-----|-------------------|
| SIEM/SOC | MTTD | Log correlation | Alert vs isolate | Detection exists, response is manual-only |
| CI/CD gates | Pipeline timeout | SAST/DAST results | Skip vs break build | Fail-open on timeout; sign before scan |
| Authentication | Lockout window | Failed attempts | CAPTCHA vs lockout | Session granted before all checks complete |
| Rate limiting | Rate window | Request patterns | Degrade vs deny | Burst completes objective in one window |
| Human approval | Approval latency | Request context | Approve vs deny | Queue pressure → rubber stamps |

### 3.2 Extended Domains

| Domain | W_j | E(t) | C_j | Failure Signature | Scanner Hooks |
|--------|-----|------|-----|-------------------|---------------|
| Fraud/risk scoring | Scoring latency vs txn TTL | Device fingerprint, velocity, chargebacks | Approve/hold/step-up | Commitment before evidence; async "later" checks that never gate | `log + continue` patterns; background task without enforcement callback |
| Incident response | Detection → containment lag | Alerts, heuristics, correlation confidence | Quarantine/cut creds/rotate | Alerting exists but containment is manual-only and queue-bound | `notify-only` paths; no automatic guard on high-confidence triggers |
| Feature flags/kill switches | Propagation delay, cache TTL | Error rate, blast radius signals | Disable/rollback/partial | Kill switch exists but can't trip fast enough; stale caches keep it "on" | Config reads cached without TTL; flag checks after irreversible action |
| Supply chain/dependency | Time between "available" and "verified" | Signatures, SLSA provenance, SBOM diffs | Deploy/pin/block | Verification optional; on error, proceed | `if verify fails: warn` logic; signature checks in try/except that continues |
| Secrets/key rotation | Rotation interval vs compromise dwell | Usage anomalies, leak detectors | Revoke/rotate/force reauth | Rotation scheduled but revocation not gated; "grace period" becomes permanent | Long-lived tokens without revocation path; revocation not enforced at use sites |
| Backups/restore | Restore-point age + RTO | Backup integrity checks, restore drills | Declare recoverable / proceed | Backups exist, restore untested (documentation-as-appearance) | "Backup succeeded" without verification; destructive ops not guarded by restore proof |

---

## 4. Self-Application: Governor Approval Fatigue

**This is the self-referential failure domain.** The governor will create its own fatigue domain unless explicitly bounded. Same W / E(t) / C structure, applied to the governor's own approval flow.

### 4.1 The Risk

The governor asks humans to approve things. Under load:
- Approvals become throughput, not decisions
- Queue pressure degrades attention budget (κ_j exhaustion)
- Adversary wins by exhausting human attention
- "Approve all" drift makes the gate advisory

This is exactly the pattern the scanner catches in other code — but applied to the governor itself.

### 4.2 Approval Fatigue Invariants

| Invariant | What It Prevents | Implementation |
|-----------|-----------------|----------------|
| **Batching + aggregation** | Raw log fatigue | Approvals summarize *claim deltas*, not individual events |
| **Quorum under pressure** | Rubber-stamp risk | High-risk gates require 2-of-N when queue depth > threshold |
| **Cooldowns** | Repeated similar approvals | N similar approvals within W → require stronger evidence or pause autopilot |
| **Fail-closed under overload** | Approve-all drift | Queue > threshold → reduce action space, not increase throughput |
| **Proof-carrying approvals** | Ambiguous rubber stamps | Approval receipt references exact diff/claims reviewed |

### 4.3 Relationship to Existing Modules

- **Quorum (`quorum.py`)**: Already supports multi-agent consensus. Extend with queue-depth-aware thresholds.
- **Sybil resistance (`sybil.py`)**: Detects voting blocs. Fatigue-driven approvals look like sybil behavior.
- **Boil control (`boil.py`)**: Already has named presets with dwell times. Approval fatigue is a boil signal.
- **Receipts**: Already proof-carrying. Ensure approval receipts reference the specific claims reviewed.

---

## 5. Code Domain (Development Time)

Temporal failures at development time. The scanner flags code that accumulates temporal debt.

| Failure Domain | W_j | E(t) | C_j | What Goes Wrong |
|----------------|-----|------|-----|-----------------|
| Test coverage decay | Time since test touched production path | Coverage reports, mutation results | "Tests pass" = ship | Tests pass but don't test what changed |
| Type drift | Time between type assertion and runtime | Type checker output | Compile = safe | `as any` / `# type: ignore` accumulates |
| Dependency lag | Time between CVE publish and update | Dependabot alerts, SBOM diffs | Merge renovate PR | Vulnerability window while "waiting for review" |
| Doc staleness | Time since doc matched code | Doc-code diff, broken examples | "Docs exist" = done | README describes architecture from 6 months ago |
| API contract drift | Time between spec and implementation | OpenAPI diff, contract tests | Deploy | Spec says X, code does Y, clients break |
| Review fatigue | PR queue depth × reviewer attention | Diff size, complexity metrics | Approve | 800-line PR approved in 3 minutes |
| Dead code accumulation | Time since code path executed | Coverage, call graph analysis | "Don't delete, might need it" | Zombie code hides bugs, confuses maintainers |
| Migration incomplete | Time since migration started | Old pattern usage count | "We're migrating" | Both patterns exist forever, neither maintained |

### 5.1 Code Scanner Patterns

```
# Temporal debt markers (development time)
- TODO/FIXME older than 90 days
- `# type: ignore` without expiration/issue
- try/except that catches too broad + continues
- Feature flags without TTL
- Commented-out code (dead path preservation)
- "Temporary" workarounds with no ticket reference
- Async operations without timeout
- Retries without backoff/limit
```

---

## 6. SRE/Ops Domain (Runtime)

Every SLO violation is a temporal failure. Either detection was too slow, response was too slow, or commitment happened before verification. MTTR is literally T_detect + T_decide + T_respond. If any exceeds W (time until user impact crosses SLO), you lose.

| Failure Domain | W_j | E(t) | C_j | What Goes Wrong |
|----------------|-----|------|-----|-----------------|
| Observability lag | Metric emission → alert fire | Dashboards, log aggregation | "We're monitoring" | Already down 10 min before alert |
| Deploy verification | Deploy finish → health confirmed | Health checks, smoke tests | Rollback decision | "Deploy succeeded" but service broken |
| Capacity headroom | 80% → 100% utilization | Capacity metrics | Scale-up action | Scaling takes longer than runway |
| Config drift | Config change → audit | Drift detection, desired state diff | "It's working" | Drift accumulates, fixing is now risky |
| Incident handoff | Shift end → context transfer | Runbook state, incident timeline | "I'm handing off" | Context lost, new on-call restarts from zero |
| Runbook staleness | Last verification → now | Runbook test results | "Follow the runbook" | UI changed, runbook lies |
| Certificate expiry | Now → cert expiration | Cert inventory, expiry alerts | Renewal | Alert fires, but renewal takes 3 days |
| Backup validity | Last restore test → now | Restore drill results | "Backups run nightly" | Backup succeeds, restore fails |
| Secret rotation | Rotation → all consumers updated | Secret usage audit | Rotate | 3 services still caching old creds |
| On-call fatigue | Alert volume × shift duration | Alert frequency, ack latency | Acknowledge/resolve | Alerts become noise, real incidents missed |

### 6.1 SRE Translation Table

| Domain | SRE Translation | The Failure You've Seen |
|--------|-----------------|------------------------|
| Rate limiting | Load shedding, circuit breakers | Breaker "half-open" test lets through the request that kills you |
| Feature flags | Rollback, canary deploys | Kill switch cached for 5 minutes while incident burns |
| Incident response | Alerting → runbook → action | PagerDuty fires, human opens laptop, 20 min gone, blast radius 10x |
| Backups/restore | RTO/RPO guarantees | "Backups succeeded" but nobody tested restore in 6 months |
| Secrets rotation | Credential lifecycle | Rotated the key, 3 services still caching the old one |
| Supply chain | Dependency updates, artifact verification | `pip install` in CI pulls unverified package, deployed before scan |
| Approval fatigue | Change management, CAB | 47 changes queued, approver rubber-stamps, bad deploy sails through |

### 6.2 Ops Scanner Patterns

```
# Temporal debt markers (infra-as-code / config)
- Alerts with no runbook link
- Timeouts set to 0 or MAX_INT
- Health checks with > 60s interval
- TTLs longer than rotation intervals
- Grace periods longer than detection windows
- Retry policies without circuit breakers
- Log retention shorter than audit requirements
- Manual-only remediation paths
- Config without drift detection
```

### 6.3 SRE Mode (Future)

The governor could have an explicit SRE mode that tracks:
- Time from deploy → verified healthy
- Time from alert → acknowledged → resolved
- Time from config change → validated
- Runbook last-verified timestamps

This maps directly to the existing Ops Governor (`src/ops_governor/`), which already enforces runbook verification, time window enforcement, and blast radius limits.

---

## 7. Cross-Domain Patterns

| Pattern | Code Manifestation | Ops Manifestation |
|---------|-------------------|-------------------|
| **Fail-open default** | `except: pass` | Alert → email (not page) |
| **Verification without gate** | Lint runs but doesn't block | Monitoring exists but no auto-remediation |
| **Commitment before evidence** | Deploy before tests finish | Scale-down before traffic confirms |
| **Evidence decay ignored** | Stale test, still green | Last backup "succeeded" 6 months ago |
| **Human bottleneck** | PR review queue | Change approval board |
| **Async check without callback** | Background job, no enforcement | Scan runs, results not gated |

---

## 8. Unified Scanner Catalog

What the governor should flag across all domains:

```yaml
TEMPORAL_DEBT_MARKERS:
  code:
    - waits_without_timeout
    - retries_without_backoff
    - catch_all_exception_continue
    - type_ignore_without_issue
    - todo_older_than_threshold
    - feature_flag_without_ttl
    - async_without_completion_gate

  ops:
    - alert_without_runbook
    - health_check_interval_too_long
    - ttl_exceeds_rotation_interval
    - grace_period_exceeds_detection
    - backup_without_restore_test
    - manual_only_remediation
    - config_without_drift_detection

  both:
    - fail_open_on_error
    - verification_without_gate
    - commitment_before_evidence
    - human_bottleneck_without_timeout
    - evidence_with_no_expiry
```

---

## 9. Integration Points

### 9.1 Security Scanner (`security.py`)

Add temporal pattern detection alongside existing static patterns. Same `CheckFinding` output format, same severity levels.

### 9.2 Code Interferometry (`code_interferometry.py`)

Temporal markers join existing 19 risk marker types. Multi-model comparison can detect temporal disagreements (one model uses transactions, another doesn't).

### 9.3 Evidence Gate (`evidence_gate.py`)

Custody scoring already measures Iₚ (invariant coupling). Temporal invariants (fail-closed, atomic check-act) are natural extensions.

### 9.4 CI/CD Gates (`git_governance.py`)

Pre-commit hook can flag temporal antipatterns in staged changes, same as current secrets detection.

### 9.5 Ops Governor (`src/ops_governor/`)

SRE-mode temporal tracking maps to existing runbook verification and time window enforcement.

---

## 10. Defender Instrumentation (Runtime)

Beyond static scanning, the governor could instrument runtime temporal properties:

| Metric | What It Measures | Δt Parameter |
|--------|-----------------|--------------|
| Verification latency distribution | How long receipts take to produce | W_j |
| Approval queue depth | Human bottleneck pressure | κ_j exhaustion |
| Fail-open trigger rate | How often timeouts cause allows | C_j drift |
| Commitment-verification gap | Time between write and receipt | T_commit - T_verify |

This overlaps with existing telemetry (`telemetry.py`) and regime detection (`regime.py`). The regime detector already tracks tool gain and error rate — temporal metrics extend this to security-specific signals.

---

## 11. Relationship to Existing Governor Concepts

| Governor Concept | Temporal Analog |
|-----------------|-----------------|
| NLAI (language ≠ authority) | Timing ≠ guarantee |
| Gate, not memory | Fail-closed, not fail-open |
| Receipts | Evidence of T_verify < T_commit |
| Fact decay | W_j expiry (stale evidence) |
| Operating envelopes | Commitment polarity (C_j) policy |
| Regime detection | Temporal health monitoring |

The governor is already a temporal attack surface minimizer — it forces T_verify before T_commit. This spec makes that relationship explicit and extends it to the code being governed.

---

## 12. Scope Boundaries

**In scope**: Static detection of temporal antipatterns in code and infra-as-code. Risk markers for interferometry. Instrumentation metrics for telemetry. SRE-mode temporal tracking.

**Out of scope**: Runtime race condition detection (that's a different tool class). Formal verification of concurrent systems. Automated fixing of temporal patterns.

**Not a replacement for**: Thread sanitizers, formal methods, property-based testing. This is a scanner, not a prover.

---

## 13. References

- Beck, J. "The Temporal Attack Surface: A Δt Framework for Asynchronous Security Systems." See `ingest/temporal_attack_surface.md`.
- Beck, J. "The Coherence Criterion." Zenodo, 2025. DOI: 10.5281/zenodo.17726789
- Beck, J. "Detecting Temporal Debt in Language Models and Software Systems." Zenodo, 2025. DOI: 10.5281/zenodo.17859324

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-02-06 | Initial gap spec from temporal attack surface paper |
| 0.2 | 2025-02-06 | Add 8 extended failure domains, scanner patterns, self-referential approval fatigue invariants |
| 0.3 | 2025-02-06 | Add code domain (8 dev-time failures), SRE/ops domain (10 runtime failures), cross-domain patterns, unified scanner catalog |
