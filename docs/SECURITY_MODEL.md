# Security Model

## Litmus Test

> Can a compromised UI or plugin cause an irreversible action without passing
> a deterministic core check and leaving a durable receipt?
>
> If yes, that's a bug.

---

## Trust Boundaries

**Trusted**: The governor daemon (`governor serve`). It performs admissibility checks,
produces content-addressed receipts, compiles constraints, and enforces the gate.
No mutation without a verified proposal. No receipt without deterministic evaluation.
See [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md) for the 6 non-negotiable invariants.

**Untrusted**: Everything else. UI layers (WebUI, VS Code, Guvnah, Maude), agent
instruction files, model output, user-provided "evidence", MCP tool results. These
are *proposals*, not authority. The governor verifies; it does not trust.
See [ADMISSIBILITY.md](ADMISSIBILITY.md) for the ex-ante / ex-post distinction.

**Semi-trusted**: Backend LLMs provide proposals but never authority. Signed waivers
(overrides with `--because` and `--expires`) are attributable and durable but can be
revoked. They leave scars in the ScarLedger — no silent exception path.

---

## Threat Model

**Adversarial agent**: Agent lies about evidence, claims files exist that don't,
fabricates test results. Defense: agents provide *pointers* (paths, commands), the
governor *verifies* (runs commands, hashes files, produces receipts). NLAI: language
is a proposal, not an authority.

**Compromised UI**: WebUI or extension modified to skip checks, inject prompts, hide
violations. Defense: UI cannot sign receipts, mint keys, or broaden scope. The daemon
is the only authority. Chat flows through the daemon's violation checker before reaching
the user. See [interfaces/webui.md](interfaces/webui.md).

**Compromised backend**: LLM returns malicious code, attempts prompt injection to bypass
constraints. Defense: evidence gate extracts claims from output and checks against
anchors *before* presenting to the user. Blocking violations require explicit resolution
(fix/revise/proceed). See `src/governor/evidence_gate.py`.

**Replay / tampering**: Attempt to reuse old receipts or modify receipt contents.
Defense: receipts are content-addressed (`receipt_id = H(schema_v + gate + subject_hash
+ evidence_hash + policy_hash)`). Same inputs = same ID; different inputs = different ID.
Timestamp is metadata, not identity. Receipt kernel uses append-only hash-chained events
with `prev_event_hash` linking. See [RECEIPT_KERNEL_CONTRACT.md](RECEIPT_KERNEL_CONTRACT.md).

**Side-channel**: Timing attacks on receipt system, information leakage via telemetry.
Out of scope for 2.x. Telemetry redaction hook strips 13 secret patterns pre-write.
Telemetry is local-only (JSONL files), not transmitted. See `libs/receipt_kernel/src/receipt_kernel/redact.py`.

---

## Design Principles

- **NLAI**: Language is a proposal, not an authority.
- **Gate, not memory**: Write-blocking enforcement, not advisory logging.
- **Receipts over trust**: Every gate decision produces a content-addressed receipt.
  No silent pass, no silent fail.
- **Absence-restrictive**: Missing scope axis = locked. Wildcard must be explicit `"*"`.
- **Scars over silence**: Overrides and failures are durable in the ScarLedger.
  No exception without attribution.
- **Boring patient attacker**: Assume the adversary reads source, has time, and tries
  the simple thing first. Complexity is the enemy of security.

---

## Deployment Modes

See [DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md) for transport security:

- **Local**: Unix socket or loopback. Single operator. No auth required.
- **Private**: mTLS + firewall. Team deployment. Certificate-based identity.
- **Public**: Auth gateway + audit log. Requires additional hardening (3.x).

---

## Future Work (3.x)

The [self-governance spec](../specs/core/SELF_GOVERNANCE_SPEC.md) defines the 3.x
security architecture: executor/proposer separation, admissible measurement gating,
cross-model validation quorum, and 8 hardening items pending human review. That work
is explicitly deferred — this document describes the 2.x security boundary.
