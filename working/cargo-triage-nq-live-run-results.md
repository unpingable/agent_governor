# cargo-triage — NQ-on-mac live run results (2026-06-30)

> **The feature built to diagnose failure testified by finding none.**
> NQ-on-mac is currently green, so the triage harness had nothing to eat. This run
> validated the **local custody pipeline**, not NQ-error triage.

Driver: `scratchpad/nq_triage_bundle/run_nq_triage.py` invoking the **shipped**
`governor.cargo_triage.triage_cargo_project` over the ratified `failure_triage`
worker. Model: **qwen2.5-coder:7b** on the mini. Target tree: the SECRET NQ mac port
(`/Users/claude/git/unpingable/nq`). Everything ran **on the mini**; the only seam
swapped was `LocalModelClient.complete` → a stdlib-urllib `/api/chat` client (loopback,
egress-internal by construction). The triage logic — prompt, schema gate,
authority-claim refusal, receipt shape, diagnostic splitting — is unchanged shipped code.

## Result: green port

| command | exit | diagnostics_found | triaged |
|---|---|---|---|
| `cargo check` | **0** | 0 | 0 |
| `cargo test` | **0** | 0 | 0 |

Frontier-safe corroboration (cargo's own summary lines, no source text):

- **359 passed / 0 failed / 0 ignored** across **14** test binaries.
- **129 crates compiled fresh** — a real full build, not a stale `target/` no-op.
- Toolchain: **rustc 1.96.0 (Homebrew)**, target **aarch64-apple-darwin**.
- 4 `warning:` lines (warnings do not trigger triage — `cargo.exit_code == 0`
  short-circuits `triage_cargo_result` before any model call).

The harness correctly emitted **zero diagnostics** rather than inventing work. This is
the load-bearing behavior: a triage system that hallucinates sludge when the build is
green is just Jira with a GPU.

## Custody result (the actual question)

The question was never "can Qwen fix NQ?" It was **"can the SECRET/local custody path
run against NQ without leaking transcripts or laundering authority?"** Answer: **yes.**

- **Zero frontier calls** — triage model was the local Ollama on `127.0.0.1`.
- **SECRET stayed local** — full transcripts (incl. the ~30KB `cargo test` output)
  written only to the mini (`~/nq_triage_run/out/full_{check,test}.json`); never
  returned to the frontier. Sanitization happened **on the mini** — correct, because the
  cloud model reading SSH stdout *is* the frontier.
- **Frontier saw only sanitized aggregate** — categories, counts, confidences, rustc
  error codes (`E\d{4}`); no transcripts, file paths, code, or `next_action` text.
- **Exit codes read from `subprocess.returncode`** (no `| tail` masking) —
  verification-discipline-correct; the pass/fail source is cargo's real exit status.
- **No authority laundering** — every receipt is `verdict=observe`, non-authoritative
  by construction; nothing claimed "port works / tests pass / safe to commit". (The
  "tests pass" statement in *this note* is the operator/harness reading cargo's exit
  code, not the local model.)
- **No repo mutation** except `target/` (cargo build artifacts), **no patch, no commit,
  no multi-gov.**

## Limitation

**No NQ compiler/test failures occurred, so no real-NQ triage value was measured.** The
worker's ability to read rustc-ish failures was already established by the synthetic
Rust mini-A/B (8/8, `local-candidate-ab-results.md` companion). This run added no new
triage-on-real-cargo signal — there was nothing to triage.

## Recommendation (ratified by operator 2026-06-30)

- **Park `platform_specificity` (cargo-triage Slice 1).** Designing the enum
  (`mac_only | rust_version | dependency | environment | unknown`) after a clean run
  would be fake precision against imaginary sludge. Unpark when **natural** breakage or
  a **relevant historical broken commit** appears — not manufactured breakage (inducing
  fake NQ breakage proves sabotage works, not that the enum is right).
- **Accept the custody-pipeline validation as the win.**
- **Next: synthetic conveyor S6** (handoff renderer).

## Victory stack to date

```
Local candidate worker Slice 0:   works
Live A/B (Python, 21 cases):      passes promotion bar (failure_triage RATIFIED)
Rust mini-A/B (8 cases):          surprisingly strong (better failure_kind accuracy)
NQ-on-mac live run:               green — and the SECRET-local custody path works
```

## Reproduce

Bundle + venv left armed on the mini (`~/nq_triage_run/`). To re-run on the next
toolchain bump / dependency break:

```bash
ssh mac 'cd ~/nq_triage_run/code && PYTHONPATH=. \
  ~/nq_triage_run/venv/bin/python run_nq_triage.py \
  ~/nq_triage_run/out /Users/claude/git/unpingable/nq qwen2.5-coder:7b'
```

Full SECRET reports stay on the mini; only `summary_{check,test}.json` is frontier-safe.
