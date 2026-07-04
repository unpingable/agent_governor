# v7 artifact-authority profile lane — AG wire-format draft (B7)

**Status: WORKING DRAFT — every field CANDIDATE, nothing citable.**
Drafted 2026-07-04 (transition-kernel-pickup slice B7). Stays in `working/`
per Q-B7's default; promotion to `specs/` is an operator event, not a
consequence of this draft existing.

**Lean basis (design provenance, NOT authority):** lean v7.0.0 "Artifact
Authority Profiles" (tag `b9860aa`, gap spec `docs/V7-GAP-SPEC.md` ratified
2026-07-02; read at HEAD `84d6d24`). The release is tagged but every v7
module is `Custody-Class: SCRATCH` — per the citation-tier rule the
theorems below are cited as *design provenance for the laws this lane
mirrors*, never as authority. The lane split is binding the other way:
**Lean owns profile laws and refusal theorems; AG owns JSON receipt
schemas, wire formats, runtime admission gates** (gap spec §5).

## What this is

The wire-format half of the v7 lane: JSON schemas an AG admission gate
would accept as *declarations* and *receipts* when artifacts from other
projects (NQ probe receipts, Porter courier receipts, Continuity
declaration exports, Claimdocs score receipts) approach an AG authority
boundary. The laundering move the lane exists to block, verbatim from the
gap spec: **"an artifact valid in its home project is treated as authority
in another project because it parses."**

## Vocabulary constitution (from the v7 non-claims, binding here)

- **No shared custody language.** These schemas are AG-LOCAL. Other
  projects author their own profiles in their own idiom; two profiles
  sharing field NAMES do not thereby share meanings. This draft creates no
  "Constellation Custody Protocol" (that name is retired).
- **No master profile, no universal artifact-authority schema.** Nothing
  here mediates every pair.
- **A registry may enumerate, never mediate.** No registry is built.
- **WLP is envelope-only.** Shared at the envelope layer (receipt kind,
  schema version, issuer, subject, causal parents, hashes, clock basis,
  payload digest, custody metadata, seal); never at the semantic authority
  layer. Behavioral pins for any future AG gate (doctrine lines, gap spec
  §6): WLP-valid ⇏ profile authority; parentage ⇏ derivability; signature
  ⇏ bridge-obligation discharge; same WLP kind ⇏ same authority profile;
  transport ⇏ reliance.
- **Screening, not enforcement.** Frames are local declarations a gate
  checks presented material against; frame quality (over- or
  under-declaration) is the declarant's visible burden.

## The four schemas (all `v0`, all CANDIDATE)

| schema | mirrors (Lean law, SCRATCH — provenance only) | candidate refusal (named, NOT minted) |
|---|---|---|
| `agent_governor.artifact_profile.v0` — a producer's local declaration of what an artifact kind can testify to | profiles are local; `profile_does_not_compose_for_free` | `profile_undeclared` — artifact kind approaches an authority boundary with no profile on file |
| `agent_governor.profile_bridge_receipt.v0` — pairwise, directional, paid crossing | `cross_profile_conversion_requires_bridge`; `admission_requires_jurisdiction_receipt`; bridges enter only by assumption — a gate may VERIFY a presented bridge, never synthesize one | `profile_crossing_unbridged` — cross-profile read attempted with no bridge receipt in custody |
| `agent_governor.stage_ascent_receipt.v0` — ONE rung, `to_stage = from_stage + 1` | `profile_stage_noncollapse`; `ascent_pays_every_rung` — an ascent j→k is a contiguous chain of rung receipts, each in custody; no multi-rung receipt is representable | `stage_rung_missing` — claimed stage exceeds the contiguous rung chain in custody |
| `agent_governor.jurisdiction_frame.v0` — per-vocabulary opt-in scoping of receipt species to obligations | `JurisdictionFrame`/`JurisdictionRespecting`; `unmatched_context_cannot_convert`; `UniversalReceiptFree` (total form only — no graded "too much coverage" screen, deliberately) | `receipt_out_of_jurisdiction` — presented receipt's species is not scoped to the demanded obligation; `universal_receipt_declared` — a frame declares a species scoped to every obligation |

**Refusal vocabulary discipline:** the five candidate refusal classes above
are NAMED for the future gate's design surface and are NOT added to
anything. The kernel's closed 12-kind enum is untouched (no new kinds
without operator); a future gate slice would carry these through its own
Q-decision before minting.

**Schema-inexpressible invariants (gate-enforced, documented here):** JSON
Schema cannot express `to_stage == from_stage + 1` (rung unit-step),
contiguity of a rung chain, or bridge-obligation discharge; those are
validation rules of the (unbuilt) gate. The schemas make the *shapes*
declarable; the laws live in the gate + the Lean provenance.

## Files

- `schemas/artifact_profile.v0.schema.json`
- `schemas/profile_bridge_receipt.v0.schema.json`
- `schemas/stage_ascent_receipt.v0.schema.json`
- `schemas/jurisdiction_frame.v0.schema.json`
- `examples/nq_probe_profile.specimen.json` — HYPOTHETICAL specimen of the
  gap spec's own forcing case ("AG wanting to treat an NQ probe receipt as
  admission evidence"). Not NQ's declaration; NQ authors its own profile in
  its own idiom or the crossing stays unbridged.
- `examples/nq_probe_to_ag_admission.bridge.specimen.json` — the paid
  crossing for that forcing case.
- `examples/parse_implies_authority.refusal.specimen.json` — the FORBIDDEN
  move rendered as the refusal the gate would emit: an artifact that
  *parses* (payload schema valid) attempting an authority read its profile's
  `non_authorities` forbids, with no bridge → `profile_crossing_unbridged`.

Validation (slice test): every file parses via `python3 -m json.tool`
(run 2026-07-04: 7/7 OK). The two schema-validatable specimens also
validate structurally via `jsonschema` after stripping the `_specimen_note`
field (specimens carry that note for the reader; the schemas are
closed-world `additionalProperties: false`, so a gate would refuse the note
— intended: specimens are exhibits, not gate inputs).

## Non-goals (this draft)

- **No runtime gate.** The admission gate consuming these shapes is a
  separate, forcing-cased slice (the forcing event class per the gap spec:
  a cross-project artifact actually presented as authority — e.g. an NQ
  probe receipt offered as AG admission evidence, or a Claimdocs score in
  an AG decision basis). Until that event, this draft is the named handle
  (YAGNI: record filed, build gated).
- **No issuer-level portfolio accounting** (named v7.x remainder — not
  silently solved here either).
- **No fact-checking of other projects' profiles**; a profile is a
  declaration whose quality is the declarant's burden.
