# Agent Governor — Governed-Work Specimen Corpus

> **STATUS: CANDIDATE (public-mvp S2) — not minted.**
> This README and the specimen artifacts are candidate evidence. They are not a
> ratified public claim. Promotion to a minted release is a separate human act.

---

## What a specimen is

A specimen is a checked-in snapshot of one complete governed run: the queue
record, the operator's approval act, the governed plan, the constraints, and
the work receipt the run produced. Everything is in plain JSON or Markdown.
No tool needs to run; no install is required.

**What a specimen is NOT:**
- It is not a claim that the system is production-hardened.
- It is not a proof that the operator approved by writing narration. Approval
  lives in the witness files listed in each specimen map below — those are the
  operative records, not the prose around them.
- It is not evidence that live cage execution is available. The conveyor is
  deliberately inert: `authority.commit/push/network` are all `false` in every
  queue item shown here, and the live cage (C11/seccomp) is unarmed by
  construction. This is documented honestly, not hidden as a roadmap gap.
- It is not evidence that the run was self-approving. The actor cannot green
  its own gate: `ActorOutputNormalizer` enforces this, and two separate seams
  split the approval question. The queue parser refuses to even construct an
  item unless `operator_approved: true` is set (`playbook_queue.py` — a static
  check; the parser touches no filesystem and verifies no provenance). Whether
  that approval is *witnessed* is checked later, at plan admission: the plan's
  `approval_ref` must resolve to the external witness file on disk
  (`work_container.py`, maude M-1), or admission refuses with
  `governance_approval_unverified`. A written "approved" in prose satisfies
  neither seam.

**What you can do with a specimen:**
- Read every artifact and trace the chain from "operator approved this work"
  through "here is what the run produced."
- Re-verify any digest by hand with `sha256sum` — no governor installation
  needed. The "verify it yourself" section below gives the exact commands.
- Check whether authority axes were respected: every `authority` block in every
  queue item and ReviewPacket carries `requested / granted / used` — you can
  confirm `used <= granted` without executing anything.

---

## Specimen locations

The artifacts live under `docs/campaigns/conveyor-dogfood/specimens/` in this
repo. Two specimens are currently in the corpus:

| Specimen | What it shows | Status |
|---|---|---|
| `cd2-state-index-roadmap-kind` | First conveyor run — code change to `state_index_export.py`, proposed_patch, verify-run receipts | RUN, DONE (2026-07-04) |
| `cd4-docs-normalize` | CD-4B self-drive — docs normalization pass, no_change ReviewPacket, admission receipt, WorkContainer projections | RUN, DONE (2026-07-04) |

---

## CD-4 specimen: `docs/campaigns/conveyor-dogfood/specimens/cd4-docs-normalize/`

**What ran:** a bounded docs normalization pass over `docs/playbooks/*`, session
`sess_aabb2a056f9f`, 8 min 19 s, 11 supervised tool-call interventions (10
approve, 1 deny). The outcome was `no_change`: the corpus was already normalized,
and two of the five terms the plan named are not in the vocabulary authority —
handing the operator a classified decision point rather than doing semantic damage.

### File map

| File | Object type | What it is | Refusal if malformed |
|---|---|---|---|
| `playbook.yaml` | PlaybookSpec (governed-playbook.v0) | The work definition. Specifies the kind (`procedure`), the target (`docs/playbooks/`), and the step (`normalize_terminology`). | `parse_playbook` raises a parse error — the queue item cannot be constructed at all. |
| `ration_card.json` | RationCard | Absence-restrictive resource allowlist. Every axis not listed is **locked**. `allowed_shell_commands: []` is why the `sha256sum` invocation was denied during the run. `observe_only: true` prevents any non-listed write. | Deserialization fails; RationCard construction raises a validation error. |
| `queue.json` | QueuedPlaybook | The conveyor queue item. `operator_approved: true` is the record of the operator's act, not a self-assertion. Note: `forbidden_paths` fences WRITE targets — reads are unrestricted (verified before execution). Authority axes are all `false`. | `not_operator_approved` refusal — the parser refuses to construct an unapproved item at all ("provenance does not grant approval"). |
| `operator_queued_playbook.operator_approved_2026-07-04` | ApprovalWitness | **The operative approval record.** The plan's `approval_ref` resolves against this file's filename. This is where approval lives — not in prose. The CD-1a codex review caught that a written `approved` in the plan body is prose, not a witnessed act; this file is the external witness. | `governance_approval_unverified` refusal — plan admission refuses without a resolvable witness file. |
| `plan.md` | Governed plan envelope (M-1 format) | The run descriptor. Born `candidate` per the M-1 admission rule (a compiler cannot approve its own plan by writing the word). Contains four citations verified at admission time. `governance_status: approved` is set only after the operator's acts. | `governance_not_approved` refusal — maude M-2 refuses a plan whose `governance_status` is not `approved` even when witnesses are present. |
| `review_packet.manifest.json` | ReviewPacket (review_packet.v0) | The work receipt emitted by the run. `status: no_change`; `files_changed: []`; `authority.used` all `false`. Contains the survey findings, two boundary risks, and two followups for the operator. `operator_review_required: true`. | If `used > granted` on any authority axis, `validate_review_packet_for_queue_item` returns a non-empty `issues` list. |
| `review_packet.summary.md` | Human-readable ReviewPacket surface | The operator-facing summary of the ReviewPacket. Markdown. Neither cites the other receipt surface as proof. | No enforcement; it is a display artifact. |
| `admission_receipt.json` | GateReceipt (schema v4) | Content-addressed admission decision. `gate: work_admission`, `verdict: proceed`, `receipt_role: measurement`. The `evidence_hash` binds the whole admission basis — a forged container cannot borrow this receipt for different/broader work. | A container whose digests don't match the receipt's `evidence_hash` fails `resolve_admission`. |
| `work_container.v1.json` | WorkContainer (work_container.v1) | Sealed projection of what the run may do: scope, ration, stop_conditions, acceptance criteria. `custody.digest` seals the container. `produced_receipts` links the ReviewPacket as testimony, not as admission. | A seal mismatch fails `dispatch_preflight` closed — `verify` then `resolve_admission` only, never registry state. |
| `work_container.s4b.json` | WorkContainer (S4b variant) | Same projection, with `admission_ref` bound to the actual GateReceipt `receipt_id` (`190fca6d…`) from `admission_receipt.json`. The S4b seam links the admission act to the container. | `admission_ref` mismatch between container and receipt: `resolve_admission` refuses because the receipt's evidence doesn't bind the container's basis. |
| `CD4B_DRIVE.md` | Drive receipt | The operator-seat record of what actually happened: 11 interventions, firing rules, outcome, harness break found and fixed, M-4 legibility findings. This is not the work receipt — that is the ReviewPacket. Neither cites the other as proof. | Not a governed object; informational. |
| `README.md` | Staging / run-outcome record | The specimen's own README; contains the flip procedure and run-outcome banner. | Not a governed object; informational. |

---

## CD-2 specimen: `docs/campaigns/conveyor-dogfood/specimens/cd2-state-index-roadmap-kind/`

**What ran:** the first governed conveyor run — extending `state_index_export.py`
to scan `docs/roadmaps/` and classify `tools/*.md` as a new `tool_roadmap` kind.
Outcome: `proposed_patch`; 17 live records produced; verify-run receipts attached.

### File map

| File | Object type | What it is | Refusal if malformed |
|---|---|---|---|
| `queue.json` | QueuedPlaybook | The conveyor queue item. `operator_approved: true` records the approval act. Allowed paths include `src/governor/state_index_export.py` and the test file; `docs/roadmaps/*` is WRITE-forbidden (reads unrestricted — verified against the validator before execution). | `not_operator_approved` refusal; `unknown_source_kind` refusal if the source kind is not in the closed vocabulary. |
| `approval.md` | ApprovalWitness | The approval act record. Quotes verbatim operator approval; records the latch semantics finding (specimen finding #1); records commit-authority note. The queue's `operator_approved: true` is the record, not the act itself. | No direct enforcement; the plan's `approval_ref` must resolve against a file in this directory. |
| `review_packet.json` | ReviewPacket (review_packet.v0) | The work receipt. `status: proposed_patch`; `files_changed` names six files; `authority.used` all `false`; `validate_review_packet_for_queue_item` passed with `issues: []`, `ready_for_operator_apply: true`. | If `used > granted`, the validator raises issues. If `files_changed` contains a forbidden path, fence check #5 fires. |
| `validation.json` | Validator output | The raw output of `validate_review_packet_for_queue_item`. `valid: true`, `ready_for_operator_apply: true`, `issues: []`. | This file is the evidence; the validator is the enforcement. |
| `required_test_receipt.json` | verify-run receipt (gate=verifier) | The verify-run receipt for `python3 -m pytest tests/test_state_index_export.py -q`. `verdict: pass`; `verifier_exit_observed: true`; `verifier_exit_source: child_exit`; `masked_exit_risk: false`. The masked-exit guard means a piped `| tail` would have been refused; this receipt proves the real exit code was observed. | `masked_exit_risk: true` or `verifier_exit_observed: false` in a receipt is refused at AUDIT (loop-protocol §3). |
| `fullsuite_receipt.json` | verify-run receipt (gate=verifier) | The verify-run receipt for the full test suite (`pytest tests/ -q --timeout=300`). `verdict: pass`; same exit-source guarantees. Receipt ID `ad422772…`. | Same masked-exit guard. |

---

## Verify it yourself

No install required. Every digest in the admission chain can be re-verified with
`sha256sum` against the actual files.

### CD-4 admission chain (5 digests)

The `admission_receipt.json` records four citation digests that were verified
before the run was admitted. The `work_container` files record the same digests
in `admission_basis.citations`. Re-verify them:

```sh
# from the repo root:
cd docs/campaigns/conveyor-dogfood/specimens/cd4-docs-normalize

sha256sum playbook.yaml
# Recorded in plan.md and admission_receipt.json as:
# playbook_digest: sha256:a8e2caf97e59bdacf988a3a2f73ef1f347b37dcacf513634e667c75aed481524

sha256sum ration_card.json
# Recorded as:
# ration_card_digest: sha256:c55509c5049ce7c826833c2b07101342e1225f139da05735f3615416b9249bd0

sha256sum queue.json
# Recorded as:
# queued_playbook_ref: sha256:45741e3a6600b80bf47bf0e6d5d00ee953524b6dfea1460a486337fdc225eee3

sha256sum plan.md
# Recorded in admission_receipt.json as:
# plan_ref: sha256:d0015fa46674bd806260ddede7663d07553004478f2853230d8013f00c49ac95

sha256sum review_packet.manifest.json
# Recorded in work_container.v1.json and work_container.s4b.json as:
# produced_receipts.review_packet_ref: sha256:810a39bc590a86c123ea77255421e4e8f6d80c471a5e06871de88139d6cb4901
```

**Verified 2026-07-05 — all five match.** Exact output:

```
a8e2caf97e59bdacf988a3a2f73ef1f347b37dcacf513634e667c75aed481524  playbook.yaml
c55509c5049ce7c826833c2b07101342e1225f139da05735f3615416b9249bd0  ration_card.json
45741e3a6600b80bf47bf0e6d5d00ee953524b6dfea1460a486337fdc225eee3  queue.json
d0015fa46674bd806260ddede7663d07553004478f2853230d8013f00c49ac95  plan.md
810a39bc590a86c123ea77255421e4e8f6d80c471a5e06871de88139d6cb4901  review_packet.manifest.json
```

No mismatches. No P0 findings.

### Cross-check: admission_ref links container to receipt

In `work_container.s4b.json`, the field `admission_ref` is:

```
"admission_ref": "sha256:190fca6d951351f4049da31508a99ee6d40e011b92e736a8c89d89a9aa1c468e"
```

In `admission_receipt.json`, the field `receipt.receipt_id` is:

```
"receipt_id": "190fca6d951351f4049da31508a99ee6d40e011b92e736a8c89d89a9aa1c468e"
```

They match. The S4b container is bound to the actual admission receipt, not a
floating reference.

### Authority accounting: confirm used <= granted

Open `review_packet.manifest.json`. Look at the `authority` block:

```json
"authority": {
  "requested": { "commit": false, "push": false, "network": false, ... },
  "granted":   { "commit": false, "push": false, "network": false, ... },
  "used":      { "commit": false, "push": false, "network": false, ... }
}
```

Every axis is `false` in all three tiers. `used <= granted` holds trivially.
No authority was requested, granted, or used. Any commit happens later in the
operator-authorized session lane, citing this specimen.

---

## Honest scope: what the runs proved and did NOT prove

Quoted and paraphrased from `docs/campaigns/conveyor-dogfood/STATUS.md`.

### CD-2 proved:
- The queue parser refuses invented source vocabulary (`unknown_source_kind`
  fired on a `backlog_item` source kind).
- The queue parser refuses to construct an unapproved item (`not_operator_approved`).
- A queue file is definitionally a record of approved work; candidate staging
  belongs to the M-1 envelope lane.
- The fence is write-only: the validator applies `forbidden_paths` only to
  `files_changed`, not to reads — verified against the landed law before execution.
- `validate_review_packet_for_queue_item` passed with `issues: []`; `used <= granted`
  holds with the test run attributed to the harness lane via an independent
  verify-run receipt.

### CD-2 did NOT prove:
- Anything about maude (no envelope, no M-2 — receipt-separation clause unexercised).
- Anything about the sealed-handoff / actor-normalizer path (the actor was the
  session, not an external sealed actor — `HandoffRenderer` and
  `ActorOutputNormalizer` remain exercised only by their tests at this point).
- Anything about live cage execution (inert by construction at LANDING).
- Commit authority via the conveyor (recorded in approval.md — the eventual commit
  happens in the ordinary operator-authorized session lane).

### CD-4B proved:
- A governed plan is admitted only after all four citations are independently
  verified (playbook_digest, ration_card_digest, queued_playbook_ref, approval_ref).
- The maude operator surface carried the whole loop: `run` → per-tool approve/deny
  from the declared fence → `promotion`/`diff`/`keep` all dispatched as maude
  commands. The human's role was authorization (the two flip acts) and review,
  not integration.
- `no_change` is a first-class, legible outcome — the run's value was the survey
  plus a classified decision point, not a diff.
- The `sha256sum` denial is a real product finding: a pure-read hashing helper
  was denied because the read-only allowlist (`allowed_shell_commands: []`) didn't
  name it. Fail-closed was the safe direction; the agent adapted (left optional
  `sha256` fields null) rather than fighting the gate.
- A harness break was found and honestly reported: `run <plan.md>` refused a
  governed plan whose flip had dirtied the workspace. The fix was documented but
  left uncommitted — changing the fence mid-drive would have been the human
  becoming the missing integration layer.
- The WorkContainer projection is live, not fantasy architecture: `sess_aabb2a056f9f`
  is the evidence spine for the work_container.v1 shape.

### CD-4B did NOT prove:
- Pure human-in-the-seat legibility. CD-4B was a recorded deviation: the session
  agent drove the operator's seat, not a human. Legibility observations are
  recorded as M-4 fuel with that caveat (see `CD4B_DRIVE.md §M-4 legibility
  findings`).
- Live cage execution (inert per LANDING; C11/seccomp unarmed).
- The sealed-handoff / actor-normalizer path in a live run (still exercised only
  by tests).
- Any commit or push authority from the conveyor (the ReviewPacket mints none).
- Bootstrap limits resolved: the WorkContainer system uses operator-fiat standing
  and in-process custody at this stage. These are documented limits, not hidden
  ones.

---

## Bootstrap limits (stated once, not hidden)

The custody grade of these specimens is bootstrap. From `docs/campaigns/conveyor-dogfood/LANDING.md` and STATUS.md:

- In-process custody/evidence is forgeable at this grade (the framework fences
  the SHAPE, not provenance).
- Standing is operator-fiat (no HMAC/mTLS/SPIFFE identity substrate at this stage).
- Constellation offices (linearaccountant, wicket, standing) are wired as SPEC
  harnesses, not live authority.
- Live cage dispatch (C11/seccomp, H2, agy-under-cage) is deliberately unarmed.

These are named limits. The versioning-by-custody-grade rule: the major version
digit is an authority claim; bootstrap ≠ ratified production.

---

## Source pointers for the refusal classes named in this document

| Refusal code | Source file | Test |
|---|---|---|
| `not_operator_approved` | `src/governor/playbooks/playbook_queue.py:68` | `tests/playbooks/test_playbook_queue.py:106` |
| `unknown_source_kind` | `src/governor/playbooks/playbook_queue.py:76` | `tests/playbooks/test_playbook_queue.py` |
| `governance_approval_unverified` | `src/governor/work_container.py:619` (comment); enforced in maude M-1 | `tests/test_work_container.py:271` |
| `masked_exit_risk` | `src/governor/ci.py` | `tests/test_verify.py` |

---

*Evidence, not authority. This README describes what the specimens show. It cannot
approve, commit, or ratify anything. Approval lives in the witness files.*
