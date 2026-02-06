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

### 2.2 Detection Approach

Static analysis patterns (like existing security scanner):

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
```

---

## 3. Integration Points

### 3.1 Security Scanner (`security.py`)

Add temporal pattern detection alongside existing static patterns. Same `CheckFinding` output format, same severity levels.

### 3.2 Code Interferometry (`code_interferometry.py`)

Temporal markers join existing 19 risk marker types. Multi-model comparison can detect temporal disagreements (one model uses transactions, another doesn't).

### 3.3 Maude Lite (`maude_lite.py`)

Custody scoring already measures Iₚ (invariant coupling). Temporal invariants (fail-closed, atomic check-act) are natural extensions.

### 3.4 CI/CD Gates (`git_governance.py`)

Pre-commit hook can flag temporal antipatterns in staged changes, same as current secrets detection.

---

## 4. Defender Instrumentation (Runtime)

Beyond static scanning, the governor could instrument runtime temporal properties:

| Metric | What It Measures | Δt Parameter |
|--------|-----------------|--------------|
| Verification latency distribution | How long receipts take to produce | W_j |
| Approval queue depth | Human bottleneck pressure | κ_j exhaustion |
| Fail-open trigger rate | How often timeouts cause allows | C_j drift |
| Commitment-verification gap | Time between write and receipt | T_commit - T_verify |

This overlaps with existing telemetry (`telemetry.py`) and regime detection (`regime.py`). The regime detector already tracks tool gain and error rate — temporal metrics extend this to security-specific signals.

---

## 5. Relationship to Existing Governor Concepts

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

## 6. Scope Boundaries

**In scope**: Static detection of temporal antipatterns in code. Risk markers for interferometry. Instrumentation metrics for telemetry.

**Out of scope**: Runtime race condition detection (that's a different tool class). Formal verification of concurrent systems. Automated fixing of temporal patterns.

**Not a replacement for**: Thread sanitizers, formal methods, property-based testing. This is a scanner, not a prover.

---

## 7. References

- Beck, J. "The Temporal Attack Surface: A Δt Framework for Asynchronous Security Systems." See `ingest/temporal_attack_surface.md`.
- Beck, J. "The Coherence Criterion." Zenodo, 2025. DOI: 10.5281/zenodo.17726789
- Beck, J. "Detecting Temporal Debt in Language Models and Software Systems." Zenodo, 2025. DOI: 10.5281/zenodo.17859324

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-02-06 | Initial gap spec from temporal attack surface paper |
