# Campaign — AG governed self-build loop (ag-admit + disposable conductor)

Status: **Slices 0–2 BUILT + GREEN** (2026-06-23). Slice 3 (waiver-completeness
dogfood) and Slice 4+ (earned widening) PARKED behind a witnessed promotion note.
Plan of record: `~/.claude/plans/abstract-brewing-hippo.md` (operator-approved).

## Question

> Can a candidate change be represented, preflighted, refused, repaired, admitted,
> executed, receipted, and committed — without moving planning, generation, or
> admissibility logic into the conductor?

## Forcing case

`docs/doctrine/specs_do_not_bootstrap.md` (2026-06-22) named `CandidateStep`, the
four-verdict union, and a thin `ag-admit` client as the delta, "named, not ratified — no
typed enum until a consumer exists." A disposable conductor that submits construction
steps and acts on the verdict is that consumer. The arrival of the consumer is the
ratification trigger.

## Invariant (load-bearing fence)

The conductor stays dumb. It carries a `CandidateStep`, calls `ag_admit`, branches
**only** on the returned `StepVerdict`, runs the allowed execution path, and writes
receipts. It must not decide admissibility, synthesize authority, infer waiver
completeness, parse refusals into new policy, reinterpret a verdict by substring, or
rewrite `CANNOT_TESTIFY` into `NEEDS_HUMAN`. **The gate observes touched paths from the
diff; the conductor never does.**

## Allowed

- Thin `ag_admit` adapter over the `governed_dispatch.PreflightClient` Protocol.
- A typed `StepVerdict` enum + a single centralized, tested projection in `ag_admit`.
- A narrow in-process `DiffPathScopeGate` (patch-path authority; **not** the SRE
  `ScopeGovernor` — no import, no `EscalationVerdict` coupling).
- A disposable conductor (`working/ag_admit_conductor.py`).
- A throwaway git toy repo; receipts for refusal/repair/admission/execution/commit.

## Forbidden

Self-hosting-first; conductor-side policy or planning logic; a planner in the middle;
silent waiver synthesis; "best effort" commit after refusal; widening toy→AG without a
witnessed promotion note; treating successful execution as admissibility; treating
absence of refusal as approval; daemon rewrite; **any change to `governed_dispatch`,
`PreflightClient`, admission verdict semantics, or the closed verdict/role enums** beyond
the new `ag_admit` module.

## Open (operator-fiat — resolved this session)

- Toy gate substrate = a new narrow `DiffPathScopeGate`; `ScopeGovernor` untouched.
- `StepVerdict` built as a typed enum now; projection centralized in `ag_admit`.
- `CANNOT_TESTIFY` is terminal — the conductor never escalates it to `NEEDS_HUMAN`;
  `NEEDS_HUMAN` arises **only** from an explicit source `REQUIRE_HUMAN`.

## What shipped (this session)

| Artifact | Path |
|---|---|
| `CandidateStep`, `StepVerdict`, `AdmitResult`, `ag_admit`, `DiffPathScopeGate`, centralized `project_source_verdict` | `src/governor/ag_admit.py` |
| Slice 0 tests (four-verdict projection, paths-observed-from-diff, POSIX path hardening, no-ScopeGovernor-coupling) | `tests/test_ag_admit.py` (26) |
| Disposable conductor (dumb; static verdict table; no diff parsing) | `working/ag_admit_conductor.py` |
| Slice 1 + Slice 2 tests (conductor behavior + full toy trace on real git, reconstructed from receipts) | `tests/test_ag_admit_conductor.py` (5) |

Source verdict ↔ wire boundary (the type boundary is not decorative): the gate's source
verdict rides in `PreflightDecision.raw.source_verdict`; `ag_admit` projects on that,
never on the coarse `decision` (`allow|would_block|blocked`). So `BLOCK` and
`CANNOT_TESTIFY` — both `decision="blocked"` on the wire — project distinctly.

## Exit states

- **(a) HELD:** toy trace reproducible from receipts, final commit causally linked to the
  admission receipt. ✅ achieved — `test_slice2_toy_trace_refuse_repair_admit_commit`
  asserts the sequence `step_admission(block) → step_repair → step_admission(proceed) →
  step_execution(pass) → step_commit(pass)` and the commit receipt's
  `admission_receipt_id` link (+ commit-message trailer).
- **(b) STOP:** the seam cannot carry a `CandidateStep` without daemon/planner expansion
  → return findings. (Not hit — the in-process `PreflightClient` Protocol carried it.)

## Stop conditions (campaign-level human halts — NOT runtime verdict synthesis)

Halt the campaign (a human stops it) when: a `CandidateStep` cannot be grounded in
existing signatures; a repair would change policy/admission semantics; a waiver/exception
packet is incomplete; the change touches `governed_dispatch`/`PreflightClient`/admission
verdicts/closed enums/authority semantics beyond `ag_admit`; the loop wants to widen
toy→AG; or receipts prove execution but not admissibility. These are distinct from the
runtime `StepVerdict`: the conductor never mints `NEEDS_HUMAN` from them.

## Downstream / next (PARKED — requires witnessed promotion note)

Slice 3: target the **waiver-completeness packet** (`working/packet-waiver-completeness.md`)
through the same loop, no widening beyond that packet. Its authorized surface is itself a
path allowlist — the same authority shape this toy exercised. Do not start cold; resume
from this card + the receipts.
