# Constellation Map — authority topology

> **SUPERSEDED as the canonical topology index (2026-07-26).** The operator's
> canonicalization direction of 2026-07-26 moved the current topology index to
> the cartography repository's operational-generation record; this file is
> retained as the 2026-07-13 census it was. Known falsified rows, left in
> place below: `~/git/docket` is **not** an "empty reservation" — it is the
> live canonical governed-execution office (two completed governed verticals);
> `ag_ng` (canonical authority office), `nq-ng`, `nq-witness`, and
> `nq-blackbox` are absent as nodes; and this repository itself is now the
> legacy authority implementation (see the README disposition banner).

**STATUS: CANONICAL topology index (adopted by operator ruling 2026-07-13;
filed as CANDIDATE same day).** Canonical does not mean complete — it means
this is where incompleteness is recorded. One page of topology: who owns what,
who explicitly does not, how artifacts cross seams, and where each node's
authoritative state lives. **Pointers, not duplicate state.** Assembled by
cold-start census from canonical artifacts only (evidence:
`working/constellation-census-2026-07-13.md`); every claim below carries a
source. `UNKNOWN` marks a recoverability gap — a documentation defect to fix at
the owning node, never a blank to fill by intuition.

**Altitude fence — the routing table.** Five questions, five surfaces; a
question answered on the wrong surface is duplicate authority:

| Question | Canonical surface |
|---|---|
| Who owns what, and what edges exist? | this file |
| What work areas exist across the constellation, and what wakes them? | `docs/roadmaps/` |
| Where is a multi-repo *program* in its governed sequence? | that program's `docs/PROGRAM_LEDGER.md` |
| What is the exact local campaign state? | that campaign's `STATUS.md` / re-entry artifact |
| What proves a transition? | receipts + design/adjudication records |

This file does not restate the others; if it starts to, cut it back.

## Lineage — what this absorbs by reference

No prior artifact claims canonical constellation-map status; each disclaims it.
This file is the index over the partial maps, which remain the load-bearing
detail:

- `docs/agent-governor-meta-plan.md` — planes + directional kernel (orientation).
- `docs/constellation-wire-plan.md` — physical wiring per seam; **code wins**.
- `docs/constellation-zoning.md` — deferred organs, one-way doors (PROVISIONAL,
  LLM-relay provenance, unratified).
- `docs/roadmaps/README.md` — **membership fence** (17 ACTIVE + 9 PARKED;
  directory adjacency is not membership) + per-tool roadmaps + PARKED wake
  triggers + CONSOLIDATION's operator-ratified separations.
- `~/git/governor-atlas` (`cases/constellation.yaml`) — machine-readable AG↔
  sibling edge graph with honest claim modes (`wired/specified/derived/
  candidate`). Stale 2026-06-19; refresh via `claimdocs verify-basis`.
- `~/git/cartography` — prior map venue (originally a purpose-built
  coordinator session), ARCHIVED 2026-06-14 and **absorbed by agent_gov**
  (operator ruling 2026-07-13; archival committed `b63217d`). Its filings
  remain citable as history; doctrine feedback older adopters were told to
  "file in cartography" now comes here. Intake residue:
  `working/cartography-intake-candidates-2026-06-14.md`.

## Nodes

Ownership as stated by the node's own artifacts (basis in parentheses).
Negative ownership is load-bearing: it is what keeps seams from collapsing.

| Node | Owns | Explicitly does NOT own | Canonical state lives at |
|---|---|---|---|
| **agent_gov (AG)** | adjudication/gating, claim transitions, receipts; client/harness side of every cross-repo seam; convening + coordination hub (wire-plan seam table; roadmaps hub) | sibling seam contracts — "siblings own their sides" (wire-plan §Not); NQ witness grammar, standing lapse model, LA internals (zoning §Is-not); observation truth | `docs/PROGRAM_LEDGER.md` (program), `docs/roadmaps/` (integration program) |
| **maude** (`~/git/agent_gov_ui/maude`) | terminal operator shell; bounded plan compilation + supervised execution desk | authority minting — "Maude mints no authority" (README); boundary **RATIFIED** in `docs/design/governed-shell/maude-boundary.md` (2026-07-02) | maude `ROADMAP.md` (defers to AG governed-shell campaign) |
| **NQ** (`~/git/nq-root/nq`) | testimony plane: witnessed operational testimony with explicit refusal boundaries; `origin_mode` vocabulary; `authorized` ceiling (design-only) | incident command, causal inference, endorsing/authorizing AG verdicts (`docs/NQ_RELATIONSHIP.md` non-claims) | nq `docs/working/decisions/FEATURE_HISTORY.md` (shipped) + `docs/working/gaps/` |
| **continuity** | memory plane: observe→commit→rely persistence across sessions | semantic adjudication; constellation coordination — its ROADMAP defers to AG's hub ("the view from inside") | continuity `docs/ROADMAP.md` + `docs/gaps/` |
| **spine** | index/edition rendering over status-bearing objects (read plane) | bearing or asserting status; discovery/"latest canonical" resolution (DOCTRINE.md N2/N3; "the villain is helpful search") | spine `REENTRY.md` |
| **standing** | entitlement/grant lifecycle (authority plane, with wicket) | — (no explicit negative found; UNKNOWN) | standing README + `docs/consumer-integration.md` (lab-backed, "not live testimony"); at rest pending consumer |
| **wicket** | admissibility preflight verdicts | being the source of authority — "Wicket may classify and gate. Wicket may not become the source of authority." (README) | wicket `SPEC.md` (authoritative for repo) |
| **linearaccountant** | consumable capacity / spend accounting; AG is a named consumer | minting from ALLOW; anything beyond "exactly one failure class" (README) | LA README; v0 frozen |
| **wlp** | transport plane: envelope wire format | decisions — "a decision engine (that is Wicket / Governor territory)" (README) | wlp README |
| **transition-kernel** | Rust invariant-bearing kernel offices | the whole pipeline — "No controller owns the whole sentence from observation to effect" (README); `NON_CLAIMS.md` is the negative-scope statement | tk `NEXT.md` + `docs/LEAN_OBLIGATIONS.md` (authoritative Lean-correspondence ledger) |
| **verifier (z3)** | constraint checking/classification | authorization — "`authorized` is reserved for upstream authority kernels" (README) | verifier README |
| **lean (LeanProofs)** | formal proof surface; custody classes ([1.0]/annex/scratch) that ARE the citation tiers | truth about the Python/Rust checkers ("theorems pin the semantics the checkers are supposed to have", RRP crosswalk); correspondence ledgers (consumers own those) | `docs/V9-RELEASE-LEDGER.md` + per-consumer crosswalks |
| **nightshift** | scheduling/resuming deferred agent *intent* under policy (execution plane, with AG) | being Governor (CLAUDE.md); NS→AG adapter direction only, never back (wire-plan) | nightshift `FEATURE-HISTORY.md` |
| **porter** | (design-only) governed-container substrate ABI for its own v0 design | — no AG client exists; no live path found | porter `DESIGN.md` ("authoritative for v0") |
| **governor-atlas / claimdocs** | atlas: AG claim-graph specimen; claimdocs: the engine + its own vocabulary (CHARTER) | authority over AG or the constellation — "pages explain the graph, they don't outrank it" | atlas `NEXT.md`, `REFRESH.md` |
| **rrp** (`~/git/rrp`, private) | receipt-indexed admissibility gate prototype (Python reference + Rust parity checkers, corpus-backed, ABI v1) | being a policy engine, sandbox, runtime, theorem prover, or effect executor (README); production custody (placeholder verifier seam) | rrp README §Identity + `ABI_STATUS.md`; AG view: `docs/roadmaps/tools/rrp.md`. Registered 2026-07-13 (naturalization ruling; first commit `9a0abf6`) |
| **tpki** (`~/git/tpki`, private) | temporal-authority doctrine + cross-project evidence register (dated, amendable, confidence-classed) + judgment-portability audit method; the "as-of" second-order judgment family (what previously minted verdicts still support under a changed basis/cut) | runtime state, verdict issuance, any shared executable mechanism until its own implementation gate is met (two projects needing the same *executable* adjudication); sibling defect status — siblings retain authority over their contracts (survey §anti-scope) | tpki README + `docs/cross-project-field-survey.md` (the amendable register). Registered 2026-07-16 (first commits `abf28ac` baseline corpus → `182222d` AG amendment; name provisional per README) |

Membership beyond this table (incl. the 9 PARKED residents and their wake
triggers): `docs/roadmaps/README.md` + `PARKED.md`. Non-members observed
squatting on member-shaped names: `~/git/playbooks-main` (Ansible), `~/git/
airlock` (game design), `~/git/notary`, `~/git/docket` (empty reservations).

### Unregistered nodes (negative controls — existence known, topology not recorded)

Nodes the operator confirms exist but whose identity/ownership is not yet
recoverable from committed constellation substrate. Listed so their absence is
a recorded fact, not folklore. Do NOT map them from conversational knowledge;
their first committed artifact must state identity, ownership, posture, and
canonical-state location.

*(None currently. RRP occupied this table 2026-07-13 for a few hours — filed
as census D12, then naturalized the same day: identity block + initial import
`rrp 9a0abf6`, registered above. The table stays as the protocol for the next
one.)*

## Edges

Only edges with a contract, receipt, or doctrine basis. Mode vocabulary is
governor-atlas's: **wired** (witnessed in running code) vs **specified**
(SPEC-honoring harness stub; contract pinned, transport injected). Machine
companion: `governor-atlas/cases/constellation.yaml` (refresh before relying —
census D11).

| From | verb | To | Mode | Basis |
|---|---|---|---|---|
| maude | executes-under | AG daemon (grant-use gate, `execution_request`, review packets) | **wired** | maude-boundary.md (RATIFIED); S6/S7 receipts in `PROGRAM_LEDGER.md`; maude `COMPAT.md` pin |
| AG | consumes | standing (grant verify) | specified | wire-plan seam table (`standing_client.py`, injected `verify_fn`) |
| AG | consumes | wicket (admissibility preflight) | specified | wire-plan (`wicket_client.py`) |
| AG | consumes | linearaccountant (capacity request/consume; never mints) | specified | wire-plan (`linear_accountant_client.py`); LA README names AG as consumer |
| AG | consumes + gates | NQ testimony (`nq.finding_snapshot.v1`; origin_mode fence decides operational effect) | wired at drill substrate; adapter contracts DESIGN-ONLY | `docs/NQ_RELATIONSHIP.md`; `drill_runner.py`; nq `TESTIMONY_AUTHORIZATION_ADAPTER.md` (v0, design-only) |
| nightshift | proposes-to | AG (NS→AG translation; one-way) | specified | wire-plan (`nightshift_adapter.py`) |
| continuity | persists-for | AG (pinned consumer surface) | contract V1 implemented; reliance queries unwired from AG | continuity `PINNED_CONSUMER_SURFACE_GAP.md`; roadmaps hub drift column |
| continuity | exports-to | spine (declaration export) | contract frozen; adapter slice NEXT | continuity `DECLARATION_EXPORT_V0.md`; spine REENTRY |
| transition-kernel | obligates | lean (Rust↔Lean correspondence) | ledgered | tk `docs/LEAN_OBLIGATIONS.md` (authoritative); lean crosswalk is the inverse index |
| AG | cites | lean (refusal-class theorems, citation tiers) | wired (citation discipline) | `src/governor/proof_seam.py`; lean `Admissibility/README.md` custody classes |
| constellation-artifacts | supplies-specimen-to | NQ (declared-deny lab, Step-0 check) | receipted, lab decommissioned 2026-06-27 | constellation-artifacts manifests + TEARDOWN receipts |
| governor-atlas | indexes | AG (claim graph; specified-vs-wired) | observing only | atlas README ("docs that fail closed") |
| lean | pins-semantics-for | rrp (checker semantics crosswalk; proves nothing about the code) | documented both sides | lean `docs/RRP-LEAN-CROSSWALK.md` (2026-07-09); rrp README §Identity |

**Not edges** (recorded so they stop being re-derived): the nq-witness 5-layer
role table (Witness→NQ→Night Shift→Governor→Human) is unilateral, unreciprocated
(census D4); repos mentioning each other in prose; anything pointing at
`~/git/cartography/coordination/` (archived venue, census D1).

## Work topology — where authoritative backlog state lives

There is deliberately no universal backlog. Pointer table only:

| Altitude | Home | What it answers |
|---|---|---|
| Program state (active roads, NEXT, receipts) | `docs/PROGRAM_LEDGER.md` | where are we; what is CLOSED; the ONE NEXT |
| Integration portfolio (posture, wake conditions, drift) | `docs/roadmaps/` (hub + tools/ + PARKED + CONSOLIDATION) | which repos, what state, what wakes them |
| Campaign threads | `docs/campaigns/*/STATUS.md` | per-campaign slice state (D7: not yet cross-linked to the ledger) |
| Per-node local backlog | each node's column in §Nodes | node-internal gaps/roadmaps |
| Cross-repo gap leads (stale snapshot) | `~/git/gap-backlog-inventory.codex.jsonl` | lead list only — 236 rows, already stale at generation (census D9) |

## UNKNOWN / defects

Live recoverability gaps, numbered in the census note (D1–D12; resolutions
recorded there): nq-witness role table unreciprocated (D4) ·
Driftwatch/Labelwatch ownership unrecoverable — retained as a gap, not awarded
by mention-frequency (D5) · continuity MCP schema error — a live substrate
defect owed its own repair slice, not cartographic cleanup (D6) ·
PROGRAM_LEDGER scope + ingress insufficiently declared — relevant campaigns
should cite it; unrelated campaigns must not be conscripted (D7) · `~/git`
root indices contradict each other (D8) · atlas edge-graph unverified since
2026-06-19 (D11) · 8 backlog stubs carry UNKNOWN reconciliation confidence
(run `python3 scripts/portfolio_report.py` for the live list). Resolved
2026-07-13: D1 (cartography archival committed, wicket/wlp repointed;
standing residue noted in census), D2/D3 (staleness headers added), D9
(superseded by the reconciled `.governor/backlog/` projection), D12 (RRP
naturalized — `rrp 9a0abf6`).

## Maintenance rule

This file changes only when an ownership claim, negative claim, or edge
changes at its source — it follows the artifacts, never leads them. A new edge
requires a contract/receipt/doctrine basis at the owning nodes first. If this
file and a node's own artifact disagree, the node's artifact wins; fix this
file. Ratification of this map (CANDIDATE → minted) is an operator act.
