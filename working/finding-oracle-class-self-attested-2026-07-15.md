# Finding — the oracle independence class is self-attested

**ID:** `oracle-class-self-attested`
**Filed:** 2026-07-15
**Status:** **FINDING — requires an operator ruling; authorizes no implementation**
**Class:** evidence-custody seam / latent laundering path
**Provenance:** surfaced auditing the `composer-pack-code` candidate ("audit
before building, expect completion-redshift"). The audit found a gap instead.

## The finding

`oracle_class` — the independence ladder the kernel grades witnesses on — is
a number the witness **declares about itself**. Nothing derives it; nothing
verifies it.

The ladder (`libs/receipt_kernel/.../oracle_independence.py`):

```text
0 — local, same host (e.g. pytest on the dev machine)
1 — same-org CI
2 — cross-org CI
3 — independent third-party verification
```

The full path, traced:

| # | site | what happens |
|---|---|---|
| 1 | `src/governor/oracle_pytest.py:284-291` | `OraclePytestRunner.__init__(*, oracle_class: int = 0)` — **a constructor parameter**. The caller states the class. |
| 2 | `oracle_pytest.py:364` | `OraclePytestLog(oracle_class=self.oracle_class, ...)` — copied through verbatim. |
| 3 | `src/governor/evidence_gate.py:1181` | `"oracle_class": getattr(oracle, "oracle_class", 0)` → written into evidence blob `meta`. |
| 4 | `libs/receipt_kernel/.../_helpers.py:89` | `build_blob_class_map` reads `meta.oracle_class` back. |
| 5 | `.../oracle_independence.py` | the invariant grades the claim on that number. |
| 6 | `src/governor/release_taint.py:40-44` | `publish_min_class` compares against it at the **publish boundary**. |

So `OraclePytestRunner(oracle_class=3)` on a laptop produces evidence that
says *"independent third-party verification"*, and every consumer downstream
believes it. **This is `Belief.source="witnessed"` in a hard hat** — the exact
crime the fiction slice closed hours earlier, in the domain that is supposed
to be the strong-witness one.

Worse in one respect than the fiction case: `_capture_environment()`
(`oracle_pytest.py:230`) captures `python_version` / `platform` / `machine`,
and `_capture_git_state` captures commit/branch/dirty — but **no CI
indicators**. So the evidence needed to *derive* even class 0 vs class 1
isn't collected. The number has no independent basis to check against, not
merely no check.

## Severity: LATENT, not live — do not panic-fix

- `oracle_independence` "ships with all thresholds at class 0, so it's inert
  today" (its own docstring). Nothing currently refuses on the number.
- The module honestly documents its own simplifications
  (max-class-over-all-oracles; no oracle-presence enforcement) — this is
  known-incomplete territory, not a hidden bug.
- Nothing in-repo passes a non-zero `oracle_class` (default `0` everywhere
  checked).

**It becomes live the moment anyone does what the docstring invites**:
*"When a project raises the bar (e.g. strict + security-sensitive → class 1),
claims backed only by class-0 oracles will fail this invariant."* On that day
the gate is enforcing a self-declared integer, and passing it is `oracle_class=1`.

## Why this is NOT being fixed in-session

Register discipline: the fix touches **receipt-kernel constitutional
invariants** and the **publish/release boundary** — both named items on the
custody-affecting list. That is a ruling, not an edit, and specifically not
one to make at the end of a long session on the strength of a fresh
discovery. The finding is the deliverable.

## Options (for the ruling; none adopted)

1. **Derive what is derivable.** Capture CI/runner indicators in
   `_capture_environment()` and compute class 0-vs-1 mechanically; classes 2–3
   remain unattestable locally and must be minted by whoever actually
   witnessed (a CI receipt, a third-party attestation). Additive, no kernel
   change, and it is the precondition for any real fix.
2. **Type the claim honestly.** `oracle_class: int` → a closed vocabulary
   distinguishing *derived* from *asserted* (e.g.
   `Independence = DerivedLocal | DerivedCI{evidence} | Asserted{class, by}`),
   so an asserted class is visibly asserted and a threshold can refuse to
   count it. Same law as `TransmissionPath`, `RefusalKind`, `operator_mode`,
   the axis vocabulary — the fifth-plus instance. Kernel-adjacent → ratify.
3. **Fence the threshold instead.** Leave the number, but make
   `oracle_independence` / `release_taint` refuse to enforce a minimum above
   0 while classes are self-attested — fail-closed on the *policy*, not the
   datum. Smallest honest move; keeps the ladder inert until it is earned.
4. **Rule it acceptable.** The runner is in-process and trusted; the class is
   operator-set configuration, not agent testimony. Legitimate — but then the
   docstring's "raise the bar" invitation needs a warning that the bar is
   made of paper, and `release_taint` should say so at the publish boundary.

Drafter's lean: **1 + 3** (capture the derivable evidence; fence the policy so
the ladder cannot be raised onto an unearned datum), leaving 2 for when a
consumer actually needs classes 2–3.

## Stop lines

- No kernel invariant edited without a ruling.
- No change to the publish threshold's semantics.
- This finding says nothing about `confidence.sanity`,
  `claims_evidence_binding`, or the other 11 invariants; they were not audited.
- The `composer-pack-code` candidate remains **filed, unbuilt**. This audit
  found the gap it predicted; it did not authorize the pack.
