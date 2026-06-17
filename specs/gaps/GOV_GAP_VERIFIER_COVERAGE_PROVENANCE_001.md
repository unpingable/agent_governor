# GOV_GAP_VERIFIER_COVERAGE_PROVENANCE_001

## Title

Exit honesty is not coverage — a `verify-run` receipt proves the wrapped command
exited honestly, not that the changed artifact participated in the run.

## Status

**Candidate — abstraction record, authorizes no build.** Filed 2026-06-17 from an
external forcing case: the overnight Lean-loop field report
(`working/field-report-verify-run-2026-06-16.md`, §"Exit-honesty ≠ coverage").
A real run hit the failure shape — `lake build` returned 0 while a just-added
module *looked* unbuilt. The reported instance was a local `ls` path bug, but the
class is real: **a default build target that excludes a file yields a true-green
that never compiled the changed file.** The honest exit code is necessary but not
sufficient.

## Doctrine (load-bearing — belongs verbatim in any implementation)

> A verifier receipt attests execution and exit status. Coverage and domain
> adequacy remain explicit non-discharge claims unless separately witnessed.

This gap exists to *name* the non-discharge, not to discharge it. A later session
must not "close" coverage by widening what `verify_run` claims; coverage is a
distinct witness with its own evidence, or it is `unknown`.

## What exists

- `src/governor/verify.py` — `verify_run()` wraps `ci_wrap` with a pre-flight
  command-safety analysis (`analyze_command`). It records `verifier_exit_observed`
  / `verifier_exit_source` / `masked_exit_risk` and the child's real exit code.
  It records **nothing** about which files/targets the command actually touched.
- `src/governor/ci.py` — `ci_wrap` captures stdout/stderr hashes, git sha, dirty
  flag, exit code. No coverage/target concept.
- The verifier-wrapper doctrine (`docs/loop-protocol.md` §3) is exit-source-honest
  by construction; coverage was always out of its stated scope. This gap makes the
  silence explicit rather than implied.

## What needs framing (not building)

A **coverage-provenance companion** to the exit receipt: a record of *what the
verifier touched* relative to *what changed*. Candidate shape (not ratified):

- Inputs the verifier is asserted to cover (changed files / targets / test ids).
- What the run actually exercised (compiled units, executed test ids, touched
  paths) — sourced from the tool's own machine output where available, never
  inferred from the exit code.
- A tri-state per changed artifact: `covered` / `not_covered` / `unknown`
  (`unknown` is the default and is not a failure to hide — it is the honest state
  when the tool emits no coverage signal).
- Emitted as a **separate** evidence object / signal, not folded into the exit
  receipt's verdict. The exit receipt's `verdict` must keep meaning exactly "the
  command exited with this status."

## Acceptance criteria / negative tests (NOT implemented here)

- AC1: a passing exit receipt with no coverage witness reports coverage as
  `unknown`, never as `covered`.
- AC2: a changed file absent from the run's exercised set surfaces as
  `not_covered` — the green is not silently upgraded.
- AC3: coverage signal is derived from the verifier's own output, never from the
  exit code or from the agent's say-so (NLAI).
- AC4: the coverage companion cannot change the exit receipt's `receipt_id`,
  `subject_bytes`, or `verdict` — it is additive provenance, not a re-verdict.
- AC5: absence of a coverage adapter for a given tool yields `unknown`, never an
  error that blocks the (honest) exit receipt.

## Non-goals

- Building a universal coverage oracle. Coverage extraction is per-tool; this gap
  names the seam, it does not commit to N adapters.
- Making coverage a *gate*. First instance is observe-only provenance; promotion
  to blocking is a separate, hotter decision.
- Re-defining "green." Exit honesty stays exactly what it is; coverage is an
  orthogonal claim.

## Open questions

- Is coverage provenance a new signal (Signal Plane), a field on a separate
  receipt, or both?
- Per-tool adapter interface vs. a generic "exercised set" contract the tool
  reports into. (Composes with `GOV_GAP_DOMAIN_AUDIT_PROFILES_001` — domain
  profiles are the natural home for per-tool "what counts as exercised.")
