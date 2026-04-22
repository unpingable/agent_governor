---
audience: repo-local
status: active
---

# Document Registers

Status: doctrine (interpretive)
Audience: anyone writing repo docs, website copy, or public-facing
material for Governor (and, by adoption-by-reference, downstream
repos)
Purpose: name the two registers Governor already uses in practice,
and pin the rules that keep the surface layer from outrunning the
law.

> Law below, verbs above. Never let the verbs outrun the law.

## Why this exists

Governor's documentation splits into two registers, and that split
is load-bearing — not branding, not "enterprise voice vs casual
voice," not a style guide. It reflects a real distinction between
**constitutional text** (ratifiable, authoritative, grep-able) and
**operator-facing grammar** (legible at first contact).

The split already exists in practice. This document names it, pins
the rules that keep both registers honest, and gives a reference
operating verb set aligned with the standing lattice.

## The two registers

### Brutalist

- **What:** specs (`specs/gaps/`), doctrine (`docs/doctrine/`),
  ADRs (`docs/adr/`), decision artifacts
  (`docs/doctrine/decisions/`), validator contracts, policy
  declarations.
- **Job:** constitutional text. Authoritative, ratifiable, immune
  to aesthetic drift. The kind of text that survives adversarial
  reading at 3am.
- **Shape:** closed sets, frozen field schemas, acceptance criteria,
  explicit non-goals. Cursed nouns permitted where precision requires
  them. No vibes.

### Operating grammar

- **What:** root `README.md`, website copy, onboarding docs,
  first-contact material, tool UIs that render governed actions.
- **Job:** legible rendering of the brutalist layer for humans at
  first contact. A projection, not a parallel source of truth.
- **Shape:** small verb set aligned with the standing lattice.
  Enough to teach the boundary without requiring seminary.

## Honesty rules

These are what keep the surface layer from quietly becoming the
thing that's true. Every one of them is load-bearing; each one
answers a failure mode seen in adjacent products.

### 1. Brutalist wins every conflict

If the operating grammar says one thing and a brutalist artifact
says another, the brutalist artifact is correct. The operating
grammar is wrong and must be fixed. Never the reverse.

### 2. Operating verbs must map to brutalist terms

The verbs in the operating layer are a **lossy but faithful
projection** of the doctrine, not a paraphrase with vibes. The
verb set must map 1:1 onto standing-class or validator-contract
terms. "Approve," "ship," "smart," "safe," "deploy" — marketing
goo that smuggles interpretation where you need standing — is
rejected.

### 3. Authority claims must cite

Any claim in the operating layer that asserts authority, guarantee,
or binding — "Governor verifies X," "Governor refuses Y" — must
cite a brutalist source artifact by id or path. If it can't cite,
it can't claim.

### 4. May compress; may not widen

The operating layer can be **less detailed** than the brutalist
layer. It cannot claim **more power, broader scope, or simpler
guarantees** than the brutalist layer. This is the anti-convenience
clause. No "Governor keeps your data safe" when the contract says
"Governor refuses receipts missing ontology_version." Compression
is fine. Inflation is a lie.

## Reference operating verb set

Aligned with the standing lattice in `docs/doctrine/standing_and_receipts.md`.
These are suggestions; a surface may use synonyms as long as rule
#2 holds.

| Operating verb | Brutalist term | What it means |
|---|---|---|
| **inspect** | `OBSERVE` | look, read, capture, measure |
| **interpret** | `INTERPRET` | infer, diagnose, rank hypotheses |
| **propose** | `RECOMMEND` | suggest an action without binding |
| **authorize** | `AUTHORIZE` | bind the system to a verdict |
| **deny** | `AUTHORIZE` + `verdict: deny` | refuse (the governor's distinctive move) |
| **escalate** / **require review** | `AUTHORIZE` + `verdict: escalate`/`require_human` | defer to human judgment |
| **apply** / **act** | `EXECUTE` | carry out an authorized action |
| **verify** | `validation` receipt | produce a validation receipt |
| **declare** | `POLICY_DECLARE` | ratify a policy artifact |

**`deny` is not optional.** A surface that only lists affirmative
verbs hides the authority boundary and teaches users that the
system is a conveyor belt with a chat box attached.

## Non-goals

This document does **not**:

- standardize prose style globally
- force every doc into one of two buckets
- make README text authoritative for anything
- replace doctrine, specs, ADRs, or validator contracts
- mandate a specific verb list (the above is a reference, not a
  ratification)

It stays scoped to **register and authority**, not "how to write
docs."

## Examples

### Paired: policy binding

- **Brutalist** (`validator_contract.md` §8.1): "Any receipt with
  standing `AUTHORIZE` or `EXECUTE` is non-binding unless it
  includes `policy_artifact_id`, `policy_artifact_hash`, and
  `ontology_version`."
- **Operating:** "Binding actions must cite the policy they're
  acting under."

### Paired: supersession ceremony

- **Brutalist** (`decision.validator_integration.q4`): "`validator_version`
  changes land with a `policy_declaration` receipt referencing the
  prior version as `supersedes`. A `ruleset_hash` change without a
  corresponding `validator_version` bump is invalid."
- **Operating:** "Version bumps require a new ratified declaration
  attested by the prior validator."

### Paired: content-bound parents

- **Brutalist** (`validator_contract.md` §6): "Parent references
  must include `id` and `content_hash`. The validator verifies that
  the referenced parent exists and hashes to the declared value. If
  any parent hash does not match, the child is invalid."
- **Operating:** "References to prior receipts are tamper-evident."

### Rejected: a bad operating line

- "Governor safely deploys your changes."
- Rejected because: "safely" is vibes (rule #2 — not a term that
  maps to standing lattice or validator contract); "deploys" may
  skip standing distinctions (compression → widening, rule #4).
- Corrected: "Governor applies only what it has authorized, and
  produces a verification receipt for each action." (Compressed, but
  faithful — "authorize," "apply," and "verify" are doing real work
  and each maps to a brutalist term.)

## Adoption by reference

Other repos in the constellation (Continuity, NQ, Night Shift,
etc.) may **adopt this pattern by reference**. No federation
ministry is required. No central body ratifies downstream
adoption. A downstream repo that wants register discipline can
cite this document and follow rules #1–#4.

"Adopt by reference" rather than "inherit" because nothing here is
automatic. It's a pattern others can reach for when it fits their
surface; it's not a cross-repo contract.

## The residual risk

The operating layer is supposed to be legible, but it should still
preserve the sense that Governor is a governed system with refusal,
evidence, and boundaries — not a magical helper orb. If the verb
layer gets too polished, it starts hiding the scar tissue.
Resisting that hiding is part of the job.

## Compressed lines

- Law below, verbs above.
- Never let the verbs outrun the law.
- Compress is fine; widen is a lie.
- `deny` is not optional.
