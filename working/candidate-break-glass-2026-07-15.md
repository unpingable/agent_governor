# Candidate — break-glass as an alternate authorization path

**ID:** `break-glass-alternate-path`
**Filed:** 2026-07-15 (operator, end of day: *"we **may** need a break-glass
path somewhere. So that's a future gap maybe. For a few things."*)
**Status:** **CANDIDATE — named, not ratified.** No forcing case selected, no
scope ruled, nothing built.
**Provenance:** operator complaining about grok's `--yolo` (and its cousin
`--dangerously-skip-permissions`); chatty's counter-framing.

## The thesis

> **A real system needs a break-glass path.** Otherwise operators eventually
> invent one with `chmod`, environment variables, or direct database edits —
> which is just break glass minus the glass and logging.

**That is the forcing case, and it is unusual: the gap is not "we lack a
feature", it is "the feature exists whether we build it or not."** An unbuilt
break-glass is not the absence of a bypass; it is an *untyped, unwitnessed*
bypass. Same law as the rest of this estate — if you don't type it, it
happens anyway, and nothing testifies.

## The distinction (theorem-shaped)

> **Emergency authority may bypass ordinary procedure; it must not erase
> custody, scope, or accountability.**

An **alternate authorization path**, never "disable authorization". Chatty's
requirement list:

- explicit emergency reason + incident/reference ID
- narrowly enumerated effects and target scope
- hard expiry, probably minutes
- fresh human witness, ideally **stronger** than normal approval
- no persistence, no implicit renewal
- loud, immutable receipt
- mandatory post-hoc review / reconciliation
- still subject to containment and absolute prohibitions

```text
ag authorize-break-glass \
  --scope production/service-x \
  --allow restart,rollback \
  --expires-in 15m \
  --reason incident-4821
```

Not `ag --fuck-it`. Or, in chatty's rendering: *"`--sigh
--I-guess-we-are-actually-doing-this`, but it prints three pages, requires a
signed witness, and expires while you're still regretting it."*

## Relation to R4 — break-glass is the exception that proves the rule

R4 (`r4-unearned-transitions-unrepresentable`) says an unearned transition
must not be **sayable**. Break-glass looks like its counterexample and is
actually its completion:

> The emergency operation IS sayable — but only in a form that testifies.

Break-glass is not a hole in R4; it is the **typed** escape hatch. The
constellation's standing law is *allowlist the good set, typed-refuse the
novel* — applied here: don't blocklist the emergency (operators route around
it), **allowlist it with a receipt.** A break-glass that erases custody is
`--yolo` with better manners; a break-glass that costs a witness and expires
in fifteen minutes is authorization, just an expensive one.

If R4 is ruled, this record should be re-read against it: R4 decides the
shape, and break-glass is the named place where the shape is deliberately
loosened *without* loosening the testimony.

## Completion-redshift: the pattern is already built, for other surfaces

**Seventh instance today.** AG already implements chatty's requirement list —
`OverrideReceipt`'s own docstring is nearly the list verbatim:

| existing | what it already does | surface it covers |
|---|---|---|
| `overrides.py` `OverrideReceipt` | *"Scoped: only apply to paths matching the scope patterns · Expiring: have an explicit expiry time · Receipted: logged with full context including violation snapshot"* — plus `--because` reason, `governor override revoke`, `cleanup` | **invariant anchors** (code autopilot) |
| `violation_resolver.py` `ExceptionRecord` | intentional deviation, `scope` ∈ single_instance/session/project, expiry; `governor gate proceed --scope --expiry` | **evidence-gate violations** |
| `scope.py` | escalation receipts; widen exactly **one** axis per request; every grant usage logged | **locality / where an agent may act** |
| `verify.py` `--allow-masked` | the model in miniature: it does **not** disable the check — it records the bypass on the receipt (`masked_exit_risk: true`, `verifier_exit_observed: false`), and the loop doctrine makes AUDIT refuse a green carrying it | **verifier exit custody** |

**The pattern is right and already load-bearing: escape hatches that
*testify* rather than *disable*.** `--allow-masked` is the proof — the hatch
exists, is discouraged, and leaves a mark that a later gate refuses.

## The actual gap

**No break-glass on the effect path.** The surfaces above cover anchors,
violations, locality, and verifier custody. Nothing covers the runtime
authorization seam — the tool gate where `operator_mode` decides whether a
WRITE prompts (`443ff63`) and where an execution grant compresses in-envelope
calls. If an operator needs to bypass *that* under incident pressure today,
there is no typed path — which per the thesis means there is an untyped one.

Adjacent and unruled: **A-1's Option 4a** (`a1-lane-restriction-4a`) would
*refuse* ungoverned×autonomous. The moment a refusal like that exists, the
break-glass question stops being hypothetical — 4a is exactly the kind of
fence an incident wants to climb. **These two should probably be ruled in the
same breath**, or 4a ships a wall with no door and someone finds the window.

## Gates before any build

1. **A forcing case.** Operator said "may… maybe… for a few things" — that is
   a name, not a need. The estate's own rule: scars are evidence, prior art is
   evidence, *speculation is not*. The prior art here is strong (every ops
   system that lacked break-glass grew one out of `chmod`), which per
   *Scars as evidence* is admissible — but the **surface** still needs
   choosing. "For a few things" is not a scope.
2. **Ruled scope**: which seam(s)? Effect path only, or also standing/spend?
3. **The witness question is the hard one.** "Fresh human witness, ideally
   stronger than normal approval" — AG's approval witnesses today are files
   (seam B: `plan_ref = sha256(plan bytes)`). What is a *stronger-than-normal*
   witness in a single-operator estate at 3am? This is the real design
   problem, and it is unsolved. A break-glass whose witness is the same person
   who is panicking is a receipt, not a check. (Possible reading: the witness
   is not a second *person* but a second *act* — reconciliation is mandatory
   and the receipt is unignorable. Name it; don't assume it.)
4. Compose with R4 if R4 is ruled first.

## Stop lines

- Nothing built. This is a name.
- No new escape hatch is added to any existing surface on the strength of
  this record.
- The existing hatches (`--allow-masked`, `override`, `gate proceed`) are
  **not** re-litigated here; they work and they testify.
