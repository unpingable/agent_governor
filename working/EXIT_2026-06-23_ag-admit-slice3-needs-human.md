# Exit ticket — ag-admit Slice 3 (waiver-completeness dogfood) → NEEDS_HUMAN

Date: 2026-06-23. Resume from `working/campaign-ag-admit-self-build.md`,
`working/promotion-ag-admit-to-waiver-completeness.md`, and the receipts —
not from memory.

## RESOLUTION (operator decision applied, 2026-06-23)

Operator chose **Model A**. Implemented in-grant:
- `admissibility.py`: `emit_waiver_admission` + `build_clean_antecedents_unsettled` —
  "clean antecedents not certified" as a `NonDischargeClaim` of the **specific existing**
  bypassed kind. No new kind; `VALID_NON_DISCHARGE_KINDS` untouched.
- `overrides.py`: `emit_override_admission` (thin wrapper over the waiver path).
- `tests/test_waiver_admission_completeness.py`: **criteria 1, 2, 4 pinned and green**.
- Packet §4 command: `pytest tests/test_overrides.py tests/test_admissibility.py
  tests/test_waiver_admission_completeness.py -q` → **122 passed, 1 skipped, EXIT=0**.
- Strictly within grant: only `admissibility.py` + `overrides.py` + new test changed;
  `gate_receipt.py` untouched. No commit (packet §3: leave tree for operator review).

**Criterion 3 (consumer refusal) — RESOLVED via Slice 3b micro-grant** (operator-authorized
one-file widening to `ci.py`). `ci_verify` is now refuse-by-default for waiver-admission
receipts, with an explicit `accepts_waiver_admitted` opt-in that relies only on the
structurally valid waiver-admission shape (verdict=proceed + non-empty existing-kind
unsettled), never on `proceed` generally. Five pins in
`tests/test_waiver_admission_completeness.py`. **All four packet criteria now stand.**

This ticket is fully resolved; the section below is the historical NEEDS_HUMAN record.

## (historical) Verdict: criterion 3 → NEEDS_HUMAN (consumer out of fence)

Slice 3 ran the **real** waiver-completeness packet through the same `ag_admit` +
`DiffPathScopeGate` loop (`working/ag_admit_slice3_waiver.py`, exit code **2** = stopped
for human). Receipts in `working/slice3_receipts/receipts/gate_receipts.jsonl`:

| gate | verdict | meaning |
|---|---|---|
| `step_admission` | `proceed` | in-scope change (`overrides.py`) ADMITs on observed paths |
| `step_admission` | `block` | §3-forbidden change (`activation.py`) REJECTs on observed paths |
| `ag_packet_review` | `block` | campaign halt — closed-receipt-enum decision (criterion 2) |

The dumb conductor and the path gate behaved exactly as in the toy: real AG path surface
flowed through unchanged. **No special-casing.** No implementation was performed.

## Why it stopped (the load-bearing reduction)

Acceptance criterion 2 requires an `unsettled` entry meaning *"clean antecedents not
certified by this admission."* `VALID_NON_DISCHARGE_KINDS` (`gate_receipt.py:236`) is a
**closed frozenset** of six kinds — `authority`, `evidence_sufficiency`, `freshness`,
`scope`, `standing`, `consumer_reliance`. None cleanly names the general "antecedents not
certified" non-claim. Two models, exhibited (not chosen — per CLAUDE.md debugging
discipline: exhibit both before promoting either):

- **Model A (within grant, no enum change):** a waiver-admitted receipt carries the
  **specific** existing `unsettled` kind(s) for whatever antecedent it bypassed (bypassed
  an authority check → `authority`; bypassed evidence → `evidence_sufficiency`; etc.).
  No change to the closed enum. Stays inside the promotion's path grant.
- **Model B (outside grant):** add a **new general** kind (e.g. `clean_antecedents`) to
  `VALID_NON_DISCHARGE_KINDS`. This is a **closed-receipt-enum change** → on the operator's
  Slice-3 STOP list → NEEDS_HUMAN.

Choosing A vs B is a receipt-semantics decision. The loop must not make it. → **operator
decision required.**

## Discovered gap (filed, not built)

`DiffPathScopeGate` ADMITs `gate_receipt.py` on **path** grounds (it is in §2), but cannot
see that the **kind** of change (closed-enum widening) is forbidden. **Path authority ≠
semantic authority.** A real AG-on-AG loop needs a **forbidden-surface classifier**
alongside the path gate (closed-enum / verdict-semantics / conductor-authority /
governed_dispatch touch detection). Named as a candidate; deliberately not built (no
silent "while I'm here" gate). It is downstream of the next named build (self-correction
within scope).

## Operator decision required (criterion 3 hand-back) — RESOLVED: chose (a), Slice 3b

Criterion 3 wants a consumer configured `accepts_waiver_admitted=False` that refuses a
waiver/proceed receipt. **No in-fence home exists:**

- the named §2 candidates (`constraint_compiler.py`, `status_rollup.py`) do **not** branch
  on receipt verdict (grep-confirmed);
- the real verdict-branching consumer is `ci.py:472-477` (`ci_verify` requires every
  receipt `verdict == "pass"`) — **outside** the §2 grant;
- packet §8: *"Stop if no consumer currently branches on verdict → hand back rather than
  building a new consumer surface."*

> **Choose:** (a) widen the grant by one file to include `ci.py` (small, well-scoped
> consumer touch: teach `ci_verify` an `accepts_waiver_admitted` flag so a `proceed`
> receipt is refused-by-default, relied-on only when opted in); or (b) defer criterion 3
> to a follow-up packet. Either way, criteria 1/2/4 already stand on their own.

## Scope fence (what this slice did NOT do)

Criteria 1/2/4 implemented **only** in `overrides.py` + `admissibility.py` + the new test.
No change to `gate_receipt.py` / any closed enum / verdict semantics / `governed_dispatch`
/ `PreflightClient` / the conductor / `.governor/loop.json` / `ci.py`. No commit, no push
(packet §3: leave the tree for operator review). No widening beyond the one promoted packet.
