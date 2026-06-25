# Governed Playbooks — Slice 3 exit ticket

**Done 2026-06-25** (gov loop, branch `feat/playbooks-gov-loop`). The Wicket seam consumes
the three governed-playbook measurements as **evidence, not authority**. First
runtime-adjacent slice. Files: `src/governor/playbooks/admission_evidence.py` (new),
`src/governor/playbooks/__init__.py` (exports), `src/governor/wicket_client.py` (new method +
evidence-record emitter, generic `check()` byte-untouched), `tests/playbooks/test_admission_evidence.py`
(12 tests, pure verifier), `tests/test_wicket_playbook_admission.py` (7 tests, seam). Playbooks
suite + wicket callers: **210 passed, exit 0**.

## The doctrine, made mechanical

> **Certification is admissible evidence for Wicket, not authority.**

Two conjunctive gates, **in this order** — and the order *is* the doctrine:

1. **Evidence coherence** — `verify_admission_evidence` (pure, total, no I/O, mints nothing).
   The presented packet must be complete and internally coherent or admission refuses
   **before the Standing seam is ever consulted**. Coherent evidence is *necessary*.
2. **Authority** — delegates verbatim to the unchanged `WicketClient.check`. Standing decides.
   Valid evidence does **not** authorize: if Standing refuses, the whole admission refuses.
   Coherent evidence is *never sufficient*.

The verdict split nails it down: the authority decision is `verdict="pass"` under gate
`wicket_seam`; the evidence record is `verdict="observe"` under gate `wicket_playbook_evidence`,
minted only on success and citing the admission as parent. **Nothing can promote an `observe`
evidence record into a `pass` admission** — there is no code path that reads the evidence record
as a decision.

## What was built

- **`PlaybookAdmissionEvidence`** — carries the measurement **objects** (`CertifiedKindMeasurement`,
  `DependencyClosure`) plus the digest strings the caller **claims** for them. Presenting the packet
  is the opt-in to playbook-governed admission.
- **`verify_admission_evidence(ev) -> EvidenceBindingResult`** — NLAI applied to evidence: it
  **re-derives** each digest from the object (`certified_kind_measurement_digest`,
  `dependency_closure_digest`) and **never trusts the claimed string**. Closed reason vocabulary
  (`BINDING_REASONS`): `evidence_incomplete`, `spec_digest_malformed`, `cert_not_bound_to_spec`,
  `cert_digest_tampered`, `closure_not_rooted_at_spec`, `closure_root_not_member`,
  `closure_digest_tampered`.
- **`WicketClient.check_playbook_admission(cooked, evidence, *, finding_id=None)`** — the two-gate
  entry point. Binding failure → `WicketRefusal(refusal_kind="playbook_evidence_unbound")`, the one
  new seam-level refusal kind (the specific binding reason rides in the receipt bundle's
  `binding_reason`). Standing and the wicket-check callable are never touched on a binding failure.

## Acceptance criteria (operator's list — all pinned)

- **Input model distinguishes evidence from authority** — `PlaybookAdmissionEvidence` (evidence) is a
  separate argument from `CookedContext.standing_receipt_id` (authority). Generic `check()` (authority
  only) is unchanged.
- **No "certified ⇒ allowed" shortcut** — `test_coherent_evidence_absent_standing_refuses` (the boss
  fight) + `test_coherent_evidence_does_not_short_circuit_standing`.
- **Digest mismatch is a closed refusal, not a warning** — `playbook_evidence_unbound` is a typed
  `WicketRefusal` with a `verdict="block"` receipt; tamper tests pin each closed reason.
- **Dependency closure digest binds the evaluated closure, not just the named playbook** — re-derives
  the closure digest from the member set; `closure_not_rooted_at_spec` + `closure_root_not_member`.
- **Docs say exactly where the chain stops** — this ticket + the module docstring: evidence gets
  `observe`, authority gets `pass`; the chain of authority is Standing, and the evidence record is
  strictly downstream of (cites) the authority decision.
- **≥1 laundering attempt** — `TestLaunderingAttempt`: perfect evidence + absent Standing → refusal,
  wicket-check never invoked, no `observe` record minted. Plus the NLAI staple-a-real-digest-onto-a-
  different-object tamper tests in the pure layer.

## Intentionally NOT done (stop line held)

- **No Standing semantics change.** `standing_client.verify` and the generic `check()` are untouched.
- **No supervisor / activation / executor / LA wiring.** No runtime authority, no playbook execution.
  (See the Track A forcing-case note below — the seam where evidence *wants* to cross into activation
  was watched for and did **not** go live in this slice.)
- **No production resolver, registry, remote fetch, `latest`, scheduling.** Evidence carries
  already-resolved measurement objects; resolution remains the injected resolver's job (Slice 2).

## Track A forcing-case watch (per operator: B is the ingress probe for A)

Track A (transition kernel) is **inevitable, not conditional**. This slice was built watching for the
seam where Wicket's evidence judgment needs to cross into activation / supervisor / Standing grant-use.

**It did not.** Evidence coherence is decidable as a pure function over the measurement objects, *upstream*
of the authority gate, and the authority gate is the existing unchanged Standing seam. The evidence packet
never needed to consult activation or the supervisor hot path to decide coherence, and — by construction —
it must not:

> **Evidence that needs runtime authority to validate itself is already authority.**

Read this correctly, future agent: **Slice 3 did not *fail* to reach Track A — it *proved this seam should
not reach* Track A.** "The forcing case did not fire" is NOT "Track A is less important now." Track A
remains inevitable, deferred infra debt with known downstream demand. The clean ingress into it is the
*spend* slice, where a playbook-governed admission actually consumes capacity (grant-use / LA consume) —
that is the natural forcing case for the supervisor/activation pickup. This evidence seam reaching into
runtime authority would have been the model cheating, not progress.

## Next possible slice (do NOT start without operator go)

Slice 4 candidate: a playbook-governed admission that proceeds to **spend** (LA capacity consume against
the admitted action). That is the first slice that genuinely touches Track A's grant-use / activation path,
and is the proper place to surface the supervisor forcing case.
