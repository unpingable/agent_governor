# Roadmap — phosphor (gov-webui) × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/gov-webui` (HEAD `2eaed6d`, 2026-03-28; v0.5.0) · Docket:
governor-atlas constellation case · ⚠ duplicate checkout at
`~/git/backburner/gov-webui` (same HEAD) — C1 disambiguates; canonical assumed
`~/git/gov-webui`

## 1. Contract snapshot — what AG assumes today

- Split-brain architecture (its ARCHITECTURE.md): chat path over daemon RPC
  (5 methods: `chat.send`, `chat.stream`, `commit.pending`, `chat.models`,
  `chat.backend`); read/status path via **direct Python imports** from the
  governor package, enforced by parity tripwire tests (`test_parity.py`).
- COMPAT.md: tested against Governor `>=2.3.0`; RPC protocol v1.0; StatusRollup
  v1; ViewModel v2; Receipt v2.
- Builders (code/research) are Phase 0: best-effort preflight, `subprocess.run()`
  with no sandbox, labeled not-for-production.

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| AG is at 2.8.1; phosphor tested against >=2.3.0, idle since 2026-03-28 | pyproject.toml both repos; COMPAT.md | HIGH |
| Direct-import read path binds phosphor to AG internals across 5 minor versions — parity tests haven't run against 2.8.1 | ARCHITECTURE.md split-brain | HIGH |
| Only 5/88 RPC methods used; new namespaces (task/scope/stability/lanes/policy) invisible to it | daemon.py registry | INFO |

## 3. Named gaps (non-binding)

- `PHOSPHOR_COMPAT_UNVERIFIED_281` — nobody has run phosphor against AG 2.8.1;
  the direct-import path is the likely break point.

## 4. Slices

### R-PHOS-1 — compat audit vs AG 2.8.1 (record, don't fix)
tier: mechanical · executor: codex · prereq: []
- purpose: run phosphor's own test suite (incl. test_parity.py) against AG 2.8.1; record pass/fail per suite — evidence for the shell-family verdict.
- files: read-only in ~/git/gov-webui; results → reconciliation INVENTORY §2 (A7 rows).
- tests: phosphor's suite invoked bare, real exit codes recorded per suite (no piped tails).
- refusal mode: n/a (audit).
- receipt shape: one commit with the verbatim run log digest.
- stop condition: suite won't even collect (import errors) — record that AS the finding; do not patch imports.

### R-PHOS-2 — revive or absorb (blocked)
tier: conceptual · executor: fable · prereq: [R-PHOS-1, C2 UI-shell verdict]
- purpose: execute the ruling (re-pin + fix parity path, or record absorption target and retire).
- files/tests/receipts: TBD by verdict.
- stop condition: no pin bumps, no Phase-1 sandbox work, before the verdict.

## 5. Do-not-build

- No version-pin bump or parity fix ahead of the ruling (evidence first).
- No Phase-1 builder sandboxing while the shell's fate is open.
- No new state query endpoints justified solely by phosphor's direct-import
  workaround (that architecture is itself under adjudication).

## 6. Operator questions

- Folded into the UI-shell family ruling (Q-A7 / Q-C2).
