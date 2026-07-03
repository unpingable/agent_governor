# Roadmap — verifier × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/verifier` (HEAD `0155f5c`, 2026-06-11; schema 0.3.0) · Docket:
governor-atlas constellation case · AG seam: `src/governor/verifier_gate.py`
(composition boundary) + `constraint_gate.py` (Z3 sidecar caller)

## 1. Contract snapshot — what AG assumes today

- Verifier is a **boundary checker**, not a governor: compiles proposals + facts
  + named constraint rules to Z3; returns explainable verdicts; owns no domain
  truth.
- Schema 0.3.0 (`Proposal.attributes` since the C-1 patch); consumer contract is
  `VERIFIER_TYPED_INPUT_PROVENANCE_GAP.md` (required reading, verifier-side).
- AG wiring: verifier_gate.py emits gate receipts (fail-open), VERIFY_SUMMARY
  signals, flake quarantine, environment fingerprint gating; 1,267-line test
  file pins the seam.

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| `GOV_GAP_VERIFIER_COVERAGE_PROVENANCE_001.md` (2026-06-17) anticipates a coordinated rollout not yet audited across consumers | AG specs/gaps + verifier repo | LOW |

## 3. Named gaps (non-binding)

- `VERIFIER_CONSUMER_CONTRACT_AUDIT` — confirm every AG call site honors the
  typed-input provenance contract at schema 0.3.0 (drift here would be silent:
  the seam fails open by design).

## 4. Slices

### R-VER-1 — consumer contract audit
tier: mechanical · executor: codex · prereq: []
- purpose: table of every AG→verifier call site vs the typed-input provenance contract + coverage-provenance gap requirements; findings only.
- files: read src/governor/{verifier_gate,constraint_gate}.py + ~/git/verifier/VERIFIER_TYPED_INPUT_PROVENANCE_GAP.md; output table → reconciliation INVENTORY §3 appendix.
- tests: `python3 -m pytest tests/test_verifier_gate.py -v` exit 0 (baseline recorded); every table row cites file:line.
- refusal mode: n/a (audit).
- receipt shape: one commit.
- stop condition: a call site violating the contract — record it; the FIX is a follow-on sandwich slice, not this audit.

## 5. Do-not-build

- Verifier stays a verdict-emitter; no governance decisions migrate into it.
- No schema-0.4 anticipation — track releases, don't lead them.
- Fail-open at this seam is a recorded design choice; changing it to fail-closed
  is an authority-semantics change (sandwich + operator).

## 6. Operator questions

None open.
