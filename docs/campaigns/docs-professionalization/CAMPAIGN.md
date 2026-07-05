# Campaign: Docs Professionalization ("a diet and a lobby")

> **Ratified by operator 2026-07-05.** Sibling of
> `docs/campaigns/nightshift-functional-mvp/`. Sequencing rule (operator +
> external review): the SMALL pre-pass runs now; the BIG consolidation runs
> after Nightshift's lane is live — docs describe the system you have, not
> the one the docs wish existed.

## The claim

Operator/end-user docs become canonical for public reading; research docs
become annexes — still there, still valuable, "not standing in the doorway
wearing a cape." The homepage carries the whole product in two lines:

> **This is a way to let AI tools help with operational work while keeping
> every action bounded, reviewable, and backed by receipts.**
> Agents can propose work. They cannot approve themselves.

## Target layout (ratified shape; agent_gov `docs/`)

```
/docs
  /start-here      what-this-is.md · 10-minute-inspect.md ·
                   30-minute-run.md · concepts.md
  /operators       maude.md · nq.md · nightshift.md · receipts.md ·
                   refusal-gallery.md · troubleshooting.md
  /integrators     work-container-v1.md · provider-contract.md ·
                   receipt-packet.md · governor-interop.md
  /reference       glossary.md · non-grants.md · limits.md · schemas.md
  /research-annex  doctrine/ · essays/ · design-notes/ · obsolete-or-parked/
```

Integrator refinements (accepted unless operator objects):
- **Link preservation is a hard rule.** Every moved file leaves a stub at
  the old path (one line: "moved to X") or the move ships with a repo-wide
  link rewrite + a mapping table in the annex. External references exist;
  404s are self-inflicted wounds.
- **Campaign/working/spec dirs do NOT move.** `docs/campaigns/`,
  `working/`, `specs/` are operational records, not reading material —
  they get an annex INDEX entry, not a relocation.

## Language rule (top-layer register — NOT a global rename)

| Internal / research | Public / operator (start-here + operators layers) |
|---|---|
| organ | component |
| constellation | system / component set |
| admissibility | what can be relied on |
| candidate | proposed / not yet accepted |
| minting | public claim / accepted claim |
| witness testimony | observed evidence |
| standing | permission / scoped authority |
| obstruction | blocked because required evidence/action is missing |
| non-grant | what agents are not allowed to do |

Deeper layers keep the precise vocabulary and introduce it AFTER the user
understands the job (glossary bridges the two). Repo-internal law
(refusal kinds, receipt fields, code) is NEVER renamed by this campaign.

## The warning (pinned): make it cleaner, not blander

The sharp parts are the product and survive every rewrite verbatim-in-force:
refusal is normal · agents do not self-approve · evidence can be stale ·
schema-valid is not admission · memory is not authority · schedule is not
consent · green tests are not total truth.

## Phase D-pre (NOW — small, bounded)

| # | Packet | Size | Worker |
|---|---|---|---|
| D-1 | Site front page: the two-line product statement above the existing custody hero (keep the hero; it's the second beat) | S | integrator |
| D-2 | `docs/start-here/` v0: what-this-is.md (the two lines + 5 short paragraphs), 10-minute-inspect.md (→ gallery + specimens + non-grants, Track A), 30-minute-run.md (→ TOUR + GOVERNED_WORKFLOW, Track B), concepts.md (the language table + the sharp parts) | M | Sonnet, integrator review |
| D-3 | glossary.html + repo glossary: add the boring-noun column (public term ↔ precise term) | S | Sonnet |
| D-4 | README front: point start-here first; demote deep sections below the fold | S | Sonnet |

## Phase D-main (GATED on nightshift-functional-mvp exit demo)

- D-5 operators/ layer (maude/nq/nightshift/receipts/troubleshooting) —
  nightshift page written against the LIVE lane, not aspiration.
- D-6 integrators/ layer (work-container v1 [ratified `74dcf86`],
  provider contract, receipt packet, interop).
- D-7 reference/ consolidation (glossary/non-grants/limits/schemas).
- D-8 research-annex migration with stubs + mapping table.
- D-9 Fable coherence + stranger-read sweep over the new lobby; external
  URL passes (ChatGPT/Gemini/web-Claude/DeepSeek) now that the site is
  pushed.

## Verifiers

Stranger-read (define-before-use, executable-literally) on every D packet;
link-checker mechanical pass after any move; the sharp-parts list is a
grep-able tripwire (each sentence must still appear, in force, somewhere in
the public layer).
