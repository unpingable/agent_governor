# GOV-GAP-CI-LANE-001: CI as a Governed Lane

Status: `shipped` (v2.6.0 — 43 tests, `governor wrap --receipt-out --ci-kind`, `governor ci verify`)

## Problem

Governor has all the enforcement machinery — `governor wrap`, gate receipts,
evidence gate, git-gov checks, provenance labels — but no declared CI lane
that makes these **required** in a pipeline. Today, CI runs tests and lints
independently of the governor. Receipts exist but nothing in CI enforces
"no receipt, no merge."

The gap is not a subsystem. It's the glue that turns Governor from "present"
into "required" in the one place teams already accept friction.

## What This Is

A **CI lane contract**: a policy pack that declares what evidence CI must
produce, a thin CLI surface to verify it, and a reference workflow shape.

## What This Is NOT

- Not a CI system (GitHub Actions / GitLab CI / Jenkins is the actuator)
- Not a new lane routing subsystem (reuses existing lane infra)
- Not provenance signing or identity binding (that's 3.x / SLSA gap)
- Not replacing `governor wrap` (extends it with receipt output)

## Existing Pieces

| What | Where | Gap |
|------|-------|----|
| Command wrapper | `wrapper.py` (`governor wrap`) | No `--receipt-out`, no `--ci-kind` |
| Gate receipts | `gate_receipt.py` | Exists, content-addressed |
| Git governance | `git_governance.py` | Has profiles (greenfield→production), `check` exits nonzero |
| Lane routing | `lanes.py` | Model-selection lanes, no CI policy lane |
| Evidence gate | `evidence_gate.py` | Has evidence kinds, custody scoring |
| Provenance labels | `provenance_labels.py` | Source classification, sensitivity hints |

## Design

### 1. `governor wrap` extensions

Add to the existing wrapper:

```
governor wrap --ci-kind <kind> --receipt-out <path> -- <cmd>
```

- Runs `<cmd>`, captures: exit code, duration, stdout/stderr hash, git SHA,
  dirty flag, Python version, command string.
- Emits a **gate receipt** to `<path>`.
- `--ci-kind` is the **explicit receipt tag** (e.g. `unit_tests`, `lint`,
  `typecheck`, `build`, `security_scan`). This is how `ci verify` identifies
  what evidence is present. No substring matching on gate names — that's
  stringly-typed and will drift the first time someone renames a step.
- Receipt fields:
  - `gate` = `"ci_wrap"` (mechanical marker, always the same)
  - `ci_kind` = the `--ci-kind` value (stored in receipt metadata)
  - `subject_hash` = H(ci_kind + cmd + git_sha + dirty)
  - `evidence_hash` = H(exit_code + stdout_hash + stderr_hash)
  - Duration, cwd, env subset (CI, PYTHONPATH, etc.) are **metadata** in
    the evidence bundle, not part of evidence_hash. Same inputs + same
    outcome = same evidence hash. Duration doesn't make two identical
    runs "different."
- `verdict` = `"pass"` if exit 0, `"block"` otherwise.
- `--receipt-out` accepts either a **file** (append JSONL) or a **directory**
  (each invocation writes `ci_wrap_<kind>_<timestamp>_<uuid>.json`).
  Directory mode scales to matrix builds without collision.
- Existing `governor wrap` behavior (file interception, approval workflow)
  remains opt-in via `--check-continuity` etc. The `--receipt-out` path is
  the minimal "just emit a receipt" mode.

### 2. CI policy pack

A CI lane defines **required receipt kinds** for `governor ci verify`:

```ini
# .governor/ci.conf (or section in daemon.conf)
[ci]
profile = production
required_kinds = unit_tests, lint
optional_kinds = typecheck, build, security_scan
```

`ci verify` checks for receipts with matching `ci_kind` values. Explicit
tags, not substring matching. If `--ci-kind` wasn't passed to `wrap`, the
receipt has no `ci_kind` and can't satisfy a required kind.

### 3. `governor ci verify`

New CLI command:

```
governor ci verify --receipts <dir-or-glob> [--policy <path>] [--receipt-out <path>] [--json]
```

- Scans receipt files in `<dir>` (JSONL or individual JSON files).
- Checks:
  1. All required kinds present (via `ci_kind` metadata)
  2. All verdicts pass
  3. No duplicate receipt IDs (replay protection)
  4. **All receipts share the same `git_sha` and `dirty=false`** — prevents
     accidentally aggregating artifacts from different checkouts
- Exits 0 on pass, 1 on failure.
- `--json` emits structured result for downstream consumption.
- `--receipt-out <path>` specifies where the meta-receipt lands. The
  meta-receipt (`gate=ci_verify`) summarizes the lane verification and
  becomes the "CI witness." If omitted, writes to the same receipts dir.
  Make the location explicit — don't invent a default and force people
  to chase it.

### 4. Git-gov integration

`governor git-gov check` already exits nonzero on blocking violations.
In CI, force production profile:

```bash
governor git-gov set-profile production
governor git-gov check
```

This makes lockfile presence, artifact integrity, and cross-index checks
**blocking** (they're warn-only in `established`). CI forces production;
dev boxes stay established. CI is the adult in the room.

### 5. Reference GitHub Actions workflow

```yaml
name: governor-ci
on:
  pull_request:
  push:
    branches: [ main ]

concurrency:
  group: governor-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install
        run: |
          python -m pip install -U pip
          pip install -e ".[dev]"

      - name: Git governance gate
        run: |
          governor git-gov set-profile production
          governor git-gov check

      - name: Tests (governed)
        run: |
          governor wrap \
            --ci-kind unit_tests \
            --receipt-out .gov/receipts/ \
            -- pytest -q

      - name: Lint (governed)
        run: |
          governor wrap \
            --ci-kind lint \
            --receipt-out .gov/receipts/ \
            -- ruff check .

      - name: Verify CI lane
        run: |
          governor ci verify \
            --receipts .gov/receipts/ \
            --receipt-out .gov/receipts/ci_verify.json

      - name: Upload receipts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: governor-receipts
          path: .gov/receipts/
```

Then: **branch protection requires `governor-ci`**. That's the moment
receipts become law. Document the branch protection step right next to the
workflow so nobody "forgets" to turn it on.

## Fork PR Considerations

- CI lane is strictly non-secret. No signing, no publishing.
- `--receipt-out` writes to local workspace only.
- Signing and publishing receipts belong to `lane=release` (triggered on
  tag push or `workflow_dispatch`), not `lane=ci`. Don't blur this boundary.

## Implementation Scope

| Item | Size | Depends On |
|------|------|-----------|
| `--receipt-out` + `--ci-kind` on `governor wrap` | S | gate_receipt.py |
| `governor ci verify` CLI command | S | gate_receipt.py, cli.py |
| CI policy pack (conf section) | S | daemon config pattern |
| Reference workflow + docs | S | above |
| Branch protection docs | XS | — |

Total: small. This is glue, not architecture.

**Implementation order:**
1. `--receipt-out` + `--ci-kind` on `governor wrap` (keep existing behavior opt-in)
2. `governor ci verify` (dir/glob input, required kinds, SHA coherence, meta-receipt)
3. Reference workflow + docs

## What This Enables

- **Receipted CI**: every pipeline run produces content-addressed proof
- **Required checks**: branch protection makes governor the gatekeeper
- **Provenance chain**: CI receipts become evidence inputs for release gates
- **SLSA foundation**: CI receipts are the first predicate in a provenance
  chain (see GOV_GAP_SLSA_001 for 3.x extension)

## Explicitly Out of Scope

- Signing receipts (3.x, requires principal_ref + auth_method)
- SLSA/in-toto/cosign integration (see GOV_GAP_SLSA_001)
- Release lane (separate gap if needed)
- Deploy lane (separate gap if needed)
- Multi-repo CI coordination (PaaS territory)
