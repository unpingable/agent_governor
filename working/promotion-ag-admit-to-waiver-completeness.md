# Promotion note — ag-admit toy path-authority → AG waiver-completeness path surface

Date: 2026-06-23. Receipt-bearing gate artifact (first artifact of Slice 3). This note
authorizes **exactly one** widening and nothing more.

## What is promoted

> The `ag_admit` + `DiffPathScopeGate` loop may now carry **one** real AG-on-AG packet —
> `working/packet-waiver-completeness.md` — declaring that packet's §2 path allowlist as
> the grant.

That is the whole grant. This does **not** authorize "AG builds AG," general self-build,
backlog auto-execution, or any second packet. Those need their own promotion notes.

## What earned it (evidence, not vibes)

The toy trace (committed `fb4322d`, witness `working/witness-ag-admit-slice2.md`) met the
mechanical promotion criteria for its class:

- a successful `refuse → repair → admit → execute → commit` trace, **reconstructed from
  receipts alone** (`test_slice2_toy_trace_refuse_repair_admit_commit`);
- **zero mutation receipts after refusal** (`test_slice2_no_mutation_receipts_when_refused`);
- the commit **causally linked** to the admission receipt (evidence ref + commit trailer);
- the gate observed paths **from the diff**, not the declared field;
- **no unknown verdict projected as admit/reject** (unknown → `CANNOT_TESTIFY`);
- **no conductor authority diffs** (conductor parses nothing, decides nothing).

One trace, one class. The promotion is correspondingly narrow: one packet.

## Authority boundary of this widening (the load-bearing fence)

This widening grants **path-scope admission authority over the §2 allowlist ONLY**:

```
src/governor/overrides.py
src/governor/admissibility.py            (waiver→receipt emission path only)
src/governor/gate_receipt.py             (only an additive unsettled reason-kind constant)
tests/test_overrides.py
tests/test_admissibility.py
tests/test_waiver_admission_completeness.py   (new)
ONE consumer read-path file               (constraint_compiler.py | status_rollup.py)
```

It explicitly does **NOT** grant authority to:

- change closed receipt enums (`VALID_VERDICTS`, `VALID_RECEIPT_ROLES`,
  **`VALID_NON_DISCHARGE_KINDS`**), or any verdict/receipt **semantics**;
- touch `governed_dispatch`, `PreflightClient`, the `StepVerdict` projection, or the
  conductor;
- mutate loop state (`.governor/loop.json`).

If executing the packet requires any of the above, the loop **stops with NEEDS_HUMAN** —
per the operator's Slice-3 stop list. Capability to patch ≠ authority over jurisdiction.

## Known boundary hit at promotion time (recorded honestly)

Reduction already run (`grep VALID_NON_DISCHARGE_KINDS src/governor/gate_receipt.py`):
the packet's **acceptance criterion 2** ("an `unsettled` entry meaning *clean antecedents
not certified*") has no clean home in the existing six closed `unsettled` kinds. It admits
two models (reuse a specific existing kind vs add a new `clean_antecedents` kind). That is
a **closed-receipt-enum decision** → NEEDS_HUMAN. See
`working/EXIT_2026-06-23_ag-admit-slice3-needs-human.md` for the two-model exhibit and the
operator decision required.

## Discovered gap (filed, not built)

The `DiffPathScopeGate` is **necessary but not sufficient** for AG-on-AG: `gate_receipt.py`
is *in* the §2 path allowlist, but the *kind* of change to it (closed-enum widening) is a
forbidden surface the path gate cannot see. A real AG-on-AG loop needs a **forbidden-surface
classifier** beside the path gate. Named here as a candidate; not built (no silent
"while I'm here" gate). It is downstream of the operator's named next build
(self-correction within scope).
