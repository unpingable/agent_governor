# Security Model

> Stub. Fill in at pre-release freeze (Pass B). Headings only — structure now, prose later.

## Litmus Test

> Can a compromised UI or plugin cause an irreversible action without passing
> a deterministic core check and leaving a durable receipt?
>
> If yes, that's a bug.

## Trust Boundaries

### What is trusted
<!-- Core governor: admissibility checks, receipt production, constraint compilation -->

### What is untrusted
<!-- UI, plugins, agent instruction files, model output, user-provided "evidence" -->

### What is semi-trusted
<!-- Backend LLMs (provide proposals, not authority), signed waivers (attributable but overridable) -->

## Threat Model

### Adversarial agent
<!-- Agent lies about evidence, claims files exist that don't, fabricates test results -->

### Compromised UI
<!-- WebUI modified to skip checks, inject prompts, hide violations -->

### Compromised backend
<!-- LLM returns malicious code, attempts to bypass constraints via prompt injection -->

### Side-channel
<!-- Timing attacks on receipt system, information leakage via telemetry -->

## Why Receipts Are Content-Addressed

<!-- Same inputs = same receipt_id. Timestamp is metadata, not identity. -->
<!-- Prevents replay, enables dedup, makes claims falsifiable. -->

## Why Waivers Leave Scars

<!-- Overrides are explicit, attributable, durable. -->
<!-- ScarLedger tracks failure provenance. No silent exception. -->

## Design Principles

<!-- Schneier-ish: threat model first, assume boring patient attacker, complexity is the enemy, security is a system property, good defaults > clever options -->
<!-- NLAI: language is a proposal, not an authority -->
<!-- Gate, not memory: blocking, not advisory -->

## Deployment Modes

<!-- See DEPLOYMENT_MODES.md for transport security (local/private/public) -->
