# Predicate Witness Infrastructure — No Authority From Predicate Satisfaction

> **Status:** constellation-facing doctrine candidate. Doc-only, **non-binding**.
> Naming/recognition artifact — names a seam the constellation has been filling
> without calling it *that*. No kernel, receipt-format, or gate change is implied.
> Ratify lazily; cite when a live predicate-bearing input forces it.
>
> **Provenance:** distilled from a cross-model thread (operator + Claude + ChatGPT
> + DeepSeek, 2026-06-25) that started from an atproto/Community-Notes screenshot
> and walked sideways into a gap in trust infrastructure. The operatic phrasings
> ("receipt for your own subjugation", "the ontology is absolute") are **dropped on
> purpose** — this is the version meant to survive contact with someone who says
> "ZK is actually useful." It is.

## 1. The surviving law (do not re-litigate)

The conjecture that survived the books, demoted from "law" to a usable form:

> **Capture resistance requires participant differentiation; privacy engineering
> decides where that differentiating information lives — but neither answers who
> authored the coordinate system that makes the differentiation meaningful.**

Trace it. Naive majority vote is captured because it treats raters as
interchangeable — one identity, one weight — so the largest coordinated bloc
wins. *Every* fix works by the same move: stop treating participants as
interchangeable, weight them by *who they are*. Bridging weights you by your
position in disagreement-space; reputation by track record; proof-of-stake by
what you put at risk; PageRank by graph position. Gaming **is** the exploitation
of indistinguishability (Sybil attacks work precisely when identities are cheap
and interchangeable — Douceur; SybilGuard moves the defense into the social
graph; EigenTrust into interaction history). So robustness consumes
**participant-distinguishing entropy**. That part is settled.

Privacy engineering then decides *who learns* that entropy:
- **public legibility** — everyone sees the profile (maximum exposure),
- **operator legibility** — the platform holds the model (institution owns the dossier),
- **mechanism-only legibility** — ZK / anonymous credentials / MPC prove a
  property without exposing the subject.

This trichotomy is real and useful. It is **not** the seam that matters here.

## 2. The seam the custody framing papers over: authorship ≠ exposure

The ZK escape — "the model moves from a stored dossier into an eligibility
predicate" — quietly assumes **the predicate already exists**. "Prove you are
cross-cleavage without revealing your position" presupposes someone *defined the
cleavage*, drew its axes, and decided what counts as spanning it. ZK protects the
**subject** from exposure. It does nothing about the **predicate** being an
*authored object*.

Two orthogonal axes, routinely conflated:
- **Exposure axis** — *who learns* the discriminant. (Public / operator / mechanism-only.)
- **Authorship axis** — *who defined* the discriminant, from what data, for what use.

A ZK-bridging system is *mechanism-only* on exposure and *maximally unilateral* on
authorship: the participant is maximally protected from being seen **and**
maximally excluded from authoring the category they are sorted into. The privacy
guarantee makes the classification *feel* consensual — you consented to *prove*
the predicate; you never consented to *the predicate*. **The cryptography can
launder unilateral category-definition into something that reads as
user-respecting.** Clean math around the wrong object.

## 3. The AG mapping: signed ≠ witnessed, applied to predicates

This is the constellation's existing witness/admissibility split arriving from
outside. A ZK proof establishes:

> "This subject satisfies predicate P."

It cannot establish:

> "Predicate P is a witnessed, admissible discriminant, fit for this use."

That is exactly **signed ≠ witnessed**: a ZK-bridging proof is a *perfectly signed
receipt for a possibly-unwitnessed classification scheme*. The subject can verify
they satisfy it; nobody can verify the *it* is anything but the operator's fiat.
It is `no_unifier_without_laundering` wearing a privacy hat — the proof layer is
the laundering step that takes an unlicensed structure (the chosen cleavage) and
makes it look like it carries authority it never earned.

**The load-bearing invariant (AG-shaped):**

> **No authority from predicate satisfaction alone.**
> A proof *satisfies* a predicate; it does not *authorize* the predicate.

Equivalently: **ZK proves satisfaction, not admissibility.** Treat a proof receipt
like any other receipt — bounded evidence of a fact, never authority to spend that
fact wherever it is presented.

## 4. The failure mode this exists to name

> **Privacy can protect the subject while laundering the category.**

The most dangerous aggregator is not the one that watches you openly — it is the
one that *defines* you privately, cryptographically seals the definition, and
makes the predicate **unreachable for contestation**. The appeal trap: in a public
classifier you can at least see your category and organize against it; in a
privacy-preserving classifier, contesting the category may require revealing the
very data the privacy protected. Privacy without predicate-contestability is a
locked room with nicer wallpaper.

Corollary, doctrine-safe form (survives "ZK is useful"):

> **Cryptography can make a classification private; it cannot make it admissible.**
> ZK is a *power amplifier for the ontology it wraps* — neutral until the wrapped
> predicate is unwitnessed, at which point it amplifies fiat.

## 5. The missing stratum: Predicate Witness Infrastructure

PKI authenticates the **speaker** and sometimes scopes the assertion (X.509
policies/EKUs, VC schemas/issuers/status). It does **not** witness the
**admissibility of the predicate** being asserted. A CA says "this key is this
entity"; an issuer says "this subject has attribute X"; a ZK proof says "this
subject satisfies P" — none says "P corresponds to a real, admissible,
contestable discriminant fit for this decision." The hard problem moved: from
*binding keys to people* to *binding assertions to reality*, and the inherited
infrastructure points the wrong way.

"Predicate PKI" is the wrong name (it summons *keys*). The right name:

> **Predicate Witness Infrastructure** — claims to *witnessed predicates* under
> *scoped consumption*, not keys to identities or claims to issuers.

The constellation has been building exactly this stratum, for agents instead of
people, without naming it *that*: NQ witnesses observations; Wicket gates
admissibility; Standing converts admitted predicates into usable authority. The
atproto block-edge was just a specimen for a hole the constellation was already
filling.

## 6. The non-collapse chain (the anti-laundering spine)

A predicate-bearing input must walk a chain, and each step **refuses the tempting
collapse**:

```
PredicateDeclaration   (what category; authored, provenanced, scoped, versioned)
      ↓   declaration ≠ witness
PredicateWitness       (independent admissibility evidence that the category is
                        real-enough for the stated claim — NOT "the model found clusters")
      ↓   witness ≠ admission
PredicateAdmission     (this predicate may be consumed for THIS claim/use — the
                        anti-laundering membrane)
      ↓   admission ≠ standing
StandingGrant / Use    (an admitted predicate becomes usable authority, scoped + expiring)
      ↓   standing ≠ spend
EffectReceipt /        (authority is consumed once, durably, for a bounded effect;
DecisionReceipt         the spend plane NEVER infers predicate legitimacy from a proof)
```

Refused collapses, named:
- declaration ≠ witness · witness ≠ admission · admission ≠ standing · standing ≠ spend
- **proof satisfaction ≠ predicate authority** · **privacy ≠ legitimacy**

Candidate carrier objects (sketch, **not** a build spec):

```
PredicateDeclaration { predicate_digest, author, intended_claim, intended_use,
                       source_basis, version/update_policy, scope_limits }
PredicateWitness     { predicate_digest, witness_kind, claim_supported,
                       admissibility_basis, limitations, expires_at }
ProofReceipt         { predicate_digest, subject_satisfies: true, disclosure_bounds,
                       verifier, issued_at }     # ZK or otherwise
```

Rule:

> A ProofReceipt may not be consumed for governance unless its `predicate_digest`
> is covered by a *fresh* PredicateWitness and *admitted for the exact claim/use*.

## 7. Constellation plane mapping (where each refusal already lives)

| Plane | Role w.r.t. predicates | Refuses |
|---|---|---|
| **NQ** (witness) | observes reality; bounded testimony ("saw X by method M at T in scope S") | authoring the category — a witness reports, it does not declare the discriminant |
| **Predicate custody** (named, owner TBD; AG/claimdocs-shaped) | holds the declaration: authorship, provenance, scope, version/digest | letting a category be used before it is declared + scoped |
| **Wicket** (admissibility) | admits a predicate-witness for a *specific* claim/use | admitting a declaration that carries no witness (the laundering membrane) |
| **Standing** | converts an admitted predicate into scoped, expiring authority | minting authority from satisfaction alone |
| **Linear Accountant** (spend) | consumes already-admitted authority for a bounded effect | inferring predicate legitimacy from a proof — never reads a proof to decide |
| **Continuity** | preserves which predicate / witness / admission / use / version, with replay boundaries | "we had a proof once" becoming immortal institutional folklore |
| **Spine** | indexes declarations, witnesses, editions, and where consumed (READ plane only) | making a predicate *true* — it helps you *find* the predicate, never authorizes it |

The big implication, stated plainly: **ZK proofs, labels, reputation scores,
simclusters, model classifications, moderation categories, trust scores, "AI
confidence", policy predicates — all enter as *declared predicates*, never as
authority-bearing facts.** Standing is where this becomes doctrine or becomes
laundering with better nouns.

## 8. This is the general form of AG's own non-collapse ladder

The governed-playbooks campaign (Track B, Slices 3–7) is a *concrete instance* of
this law. Each slice refuses one collapse, mechanically, fail-closed:

- observe ≠ pass (evidence is not authority) · pass ≠ spend · spend ≠ execution ·
  durability ≠ permission · report ≠ authority · dispatch ≠ authority.

"No authority from predicate satisfaction alone" is the same shape as
`is_authority_admission_receipt` refusing an observe-verdict evidence record as a
spend basis. The campaign already ships the spine for *its* predicates (a playbook's
certified-kind measurement); this note generalizes the shape to *any* declared
discriminant — moderation cleavages, reputation geometries, ZK eligibility
predicates — and points at the one stratum no privacy technology supplies.

## 9. The load-bearing open test (where this could still be wrong)

The honest adversary is cryptographic mechanism design. Two distinct questions,
and only the second is settled by this note:

1. **Exposure:** can a verifier check a property without learning the subject's
   position? *Yes* — ZK/anonymous-credentials do exactly this. The crude "capture
   resistance = surveillance" claim is **false**, and this note concedes it.
2. **Authorship:** can the *predicate* be admitted without an authored,
   witnessable coordinate system behind it? This note claims **no** — the predicate
   is a declared state requiring a witness, and no privacy technology supplies that
   witness; it can only hide the subject from a classification it still cannot
   authorize.

If someone exhibits a mechanism where the cleavage-geometry is itself *witnessed*
(not merely declared) **and** the witness is contestable *without* forcing subject
self-exposure, the authorship axis and the exposure axis would have been unified —
and §6's chain would need a shorter form. Until then, treat the two axes as
orthogonal and the predicate as un-admitted until witnessed.

## 10. Status / what this note does NOT do

- It does **not** add a kernel, receipt format, gate, or vocabulary. It names a
  seam and a chain; building any of §6's objects is a separate, forcing-case-gated
  decision per the owning plane.
- It is **not** anti-ZK, anti-privacy, or anti-crypto. The target is *authority
  laundering*: a proof being spent as predicate authority it never earned.
- It is filed at the AG custody root (cross-tool) as the canonical capture, not
  scattered across siblings — promotion reduces local burden, it does not duplicate
  authority. Sibling repos cite/adopt when a live predicate-bearing input forces it.

Anchors (the "survives the books" set): Douceur, *The Sybil Attack*; Yu et al.,
*SybilGuard*; Kamvar et al., *EigenTrust*; Brin & Page, *PageRank*; Wojcik et al.,
*Birdwatch / Community Notes*; *ZKlaims*; Nissenbaum, *Contextual Integrity*;
Solove, *A Taxonomy of Privacy*. AG-internal anchors: witness/admissibility split,
`no_unifier_without_laundering`, the directional one-way kernel
(`working/directional-invariants.md`), origin-mode operational fence
(signed/demonstrated ≠ operational), governed-playbooks non-collapse ladder
(`docs/playbooks/`).
