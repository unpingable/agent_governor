---
audience: governor maintainers / anyone making a release or maturity claim
status: candidate
---

# Versioning by custody grade

Status: candidate (non-binding). Captures a versioning model; ratifying it as the
binding release policy is itself a custody act (fittingly — see the rule below).
Provenance: end-of-day framing, 2026-06-30, retiring the dead axis "3.0 = AG as a
service." That was a *delivery/business-model* fence; the work reorganized around
*authority* and *custody*, and the sidecar/constellation posture demoted delivery
to packaging.

Composes with `advisory_vs_constitutional_power.md`, `proof_seam.md`
(class-not-instance), and the workflow-kernel "Bootstrap limits (documented,
accepted)" list in `.claude/rules/feature-history.md`.

---

## The rule

> **A compiled authority verb is only a candidate. A release requires custody.**
>
> Capability does not advance the version clock. *Lawful* capability at a declared
> custody grade does.

The version number is not a marketing label. It is a **governed claim about which
authority verb has crossed which custody boundary** — i.e. AG's own versioning is
an AG specimen. A major version that advanced by feature accretion has laundered
capability into a claim, which is the exact move the rest of this repo refuses.

## Two axes

### Axis 1 — authority verb (the major-version ladder)

| Major | Verb | Claim it licenses |
|------:|------|-------------------|
| 1.x | **Refuse** | AG can lawfully reject laundering / collapse. |
| 2.x | **Decide** | AG can lawfully admit/refuse governed claims. |
| 2.5 | **Expose** | AG can be publicly read/demoed without authority overclaim. |
| 3.x | **Transition** | AG can move admitted authority into bounded effect. |
| 4.x | **Delegate** | AG can hand scoped work to external/subordinate actors. |
| 5.x | **Federate** | AG can coordinate multiple governors / institutions. |

Monotone in authority — it is the one-way verb ladder, not a feature list.

### Axis 2 — custody grade (whether the verb is *lawful* yet)

| Grade | Meaning |
|-------|---------|
| `scratch` | Exploratory contact. No testimony. |
| `spec` | Shape declared, not operational. |
| `bootstrap` | Code exists, tests pass — but trust roots are operator-fiat / in-process / stubbed. |
| `real` | The authority claim survives actual custody boundaries. |
| `ratified` | Real, plus ceremony / supersession / adoption trail. |

A rung is only *reached* when its verb is lawful at `real` grade. `bootstrap` is a
**candidate**, never a release.

## Reconciling with the live semver (this is the part code-grounding forced)

The declared version is **2.8.1**, advancing on ordinary feature-semver — capability
accreting into the number, the old clock. Don't retcon it; re-base what the digits
*mean* going forward:

- **major** = a new authority verb becomes lawful **at `real` grade**.
- **minor / patch** = coverage accretion *within the current authority class*.

Under that rule 2.8.1 is honest (we are in the **Decide/Expose** era and have been
accreting coverage), and **3.0.0 is reserved** — it may not be cut until *transition*
is real-custody, regardless of how much transition machinery compiles. The major
digit is the governed claim; the minor digits are the gardening.

## Current pin (grade-annotated, code-checked 2026-06-30)

> **Declared: v2.8.1.  Authority-grade: real through Expose; bootstrap at Transition.**
> Short form: **2.5-real + 3.0-bootstrap-candidate.** *Not* "3.0-pre" — "pre" implies
> missing implementation; the implementation mostly exists, the custody under it does not.

| Rung | Code state | Grade |
|------|-----------|-------|
| 1.x Refuse | refusal classes, gate receipts, laundering walls | **real** |
| 2.x Decide | standing validator C2–C5, supersession-ratified v0.1→v0.4 | **ratified** |
| 2.5 Expose | site, glossary, demo, golden receipt corpus | **real** |
| 3.x Transition | `activation.py` four-office, governed/durable spend, `sandbox_cage.py` contract, `standing_spendability.py`, recomposition refusal | **bootstrap** ← the fence |
| 4.x Delegate | constellation adapters, SDK, daemon RPC | partial / `spec`–`bootstrap` |
| 5.x Federate | multigov-deadlock (spec-only), amendment (reserved gap) | `spec` / frontier |

AG can *transition today* — the code does it — but only at bootstrap grade:
**3.0-capable, not 3.0-lawful.**

## What 3.0 now means — the plan

Not "build admission → bounded effect" (mostly built). It is: **make the existing
loop lawful at real custody grade.** 3.0.0 cuts when *all* of these hold at `real`:

1. **Real cage backend.** `NullCage` is acceptable only as test/spec fixture; effects
   occur behind an actual enforceable boundary. (Blocked: real cage backend — the
   B-12 "decoy gate" radioactive item.)
2. **Real Standing / LA wiring.** Standing is not operator-fiat; spend is not merely
   locally typed; the authority source is externally checkable / independently
   custodied. (Today: SPEC-harness stubs + `REFUSED_DEGRADED_CLAIMS_BACKING`.)
3. **Stub retirement.** Bootstrap paths survive only as fixtures; they cannot satisfy
   a 3.0 release claim.
4. **Receipt boundary hardening.** Receipts are not forgeable merely because the
   process says so; in-process custody becomes insufficient for the 3.0 claim.
   (Relates to the Rust decision-kernel port — `rust_kernel_port_ruling`, post-launch,
   golden receipt corpus is the contract.)

Each is a gate, not a mountain: three or four **custody swaps under machinery that
already exists** — replacing the cardboard fire door with a real one, then admitting
with annoying precision that fire is hot.

## Keeper lines

> A compiled authority verb is only a candidate. A release requires custody.

> The Lean theorems prove the class boundaries; the receipt attests the instance.
> (versioning corollary: a green test proves the *capability* class; only real custody
> attests the *release* instance.)
