# Roadmap — phosphor (gov-webui) × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/agent_gov_ui/gov-webui` (HEAD `2eaed6d`, 2026-03-28; v0.5.0) · Docket:
governor-atlas constellation case · (backburner duplicate checkout removed by
operator 2026-07-02 — this path is canonical)

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
- files: read-only in ~/git/agent_gov_ui/gov-webui; results → reconciliation INVENTORY §2 (A7 rows).
- tests: phosphor's suite invoked bare, real exit codes recorded per suite (no piped tails).
- refusal mode: n/a (audit).
- receipt shape: one commit with the verbatim run log digest.
- stop condition: suite won't even collect (import errors) — record that AS the finding; do not patch imports.

### R-PHOS-2 — retire or narrow to read/status (per Q-C2-1)
tier: conceptual · executor: fable · prereq: [R-PHOS-1]
- purpose: on R-PHOS-1's evidence, execute the ruled fork: retire phosphor, or narrow it to a read/status surface (chat/builder paths dropped; the direct-import split-brain resolved in whichever direction survives).
- files: TBD by the fork taken; recommendation memo first.
- tests: TBD. · refusal mode: n/a. · receipt shape: memo commit citing R-PHOS-1.
- stop condition: any outcome that grows phosphor's surface — the ruling permits retire or NARROW only.

## 5. Do-not-build

- No version-pin bump ahead of R-PHOS-1 evidence.
- No Phase-1 builder sandboxing — builders do not survive either fork of the
  ruling.
- No new daemon endpoints justified solely by phosphor's direct-import
  workaround.

## 6. Operator questions

None open. **Q-C2-1 RULED 2026-07-02: audit, then retire or narrow to
read/status.**
