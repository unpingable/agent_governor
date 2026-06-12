# SITE_GAP_HUB_001 — the hub, dumb but structurally right

**Status: spec (build-ready). Launch-order item 3.**
Backlog: `.governor/backlog/launch-3-hub-structural.json`.
Source doctrine: `working/launch-plan-2026-06-11.md` §The site; memory `docs_ownership`
(this Claude owns the site), `launch_posture` (reduce friction, Columbo not Jobs).
Build repo: `~/git/unpingable-site` (CNAME unpingable.com). Topology source: agent_gov
(`docs/constellation-zoning.md`, `docs/reference/constellation-lexicon.md`).

## What exists

- `~/git/unpingable-site/index.html` — single hand-rolled static page (625 lines,
  no build system, CSS custom properties, Geist Mono + serif, light/dark). Content
  today: project shelf list (operational / kernels / atproto / other), research
  papers, writing links. **It is a repo list — precisely the thing the launch plan
  says the front door must stop being.** No thesis ¶, no demo, no topology, no
  component skeleton, no receipts anywhere on the page.
- `~/git/agent-governor-site` — parked domain (CNAME + one page). Plan: fold in,
  no microsite sprawl.
- Repo-side artifacts the hub can already point at (all live as of 2026-06-12):
  demo trilogy (`demo/refused-spend.sh`, `interrogate.sh`, `opa-contrast.sh`),
  golden corpus `golden/corpus/01–09`, proof seam (`proof_seam.py`, Lean
  class-boundary theorem), venv'd install path (README, this morning).

## What needs building

One commit to `unpingable-site` (plus optional `topology.html`), structured as the
spine, **with stubs allowed everywhere except the thesis and the demo pointer**:

1. **Thesis ¶ at the top** — replaces the current lede. Draft (launch plan,
   adjust rhythm only): *"Modern systems often decide faster than their evidence
   stays valid. This lab builds custody machinery for claims, standing, capacity,
   authorization, and refusal — running code plus proof artifacts that preserve
   distinctions ordinary infrastructure collapses."*
2. **The button/link directly under the thesis:** "Watch authorization fail to
   become spendability" → demo page (SITE_GAP_DEMO_PAGE_001; until that ships,
   link to the agent_gov README's Start Here anchor — never a dead link).
3. **Topology section or page** — nodes = components, **edges = the conversion
   claims** ("observation becomes claim", "standing ≠ spendability", "spend
   refused without capacity", "logs are self-report until sealed"). Stub
   rendering is acceptable (an HTML/CSS diagram or even a `<pre>` graph);
   *naming the edges is the deliverable*, prettiness is not. IA mirrors the
   actual architecture — solves the gestalt problem structurally.
4. **Component skeleton, brutally regular** — every listed component gets the
   same five fields: *what claim it handles / what it refuses / what artifact
   proves that / status (operational | research | zoned) / repo link*. Plus,
   where one exists, **one real receipt** (hash + one-line meaning; agent_gov
   corpus entries count). "What it refuses" is the differentiator — market
   boundedness. Stub value for missing fields is the literal string `zoned` or
   `—`, never invented content.
5. **Umbrella discipline** — the page is the *custody discipline / admissibility
   stack*; Agent Governor appears as one organ, not the title. Existing shelves
   (atproto, research, writing, other) survive below the new spine, demoted not
   deleted.

## Acceptance criteria

- [ ] Thesis ¶ renders above the fold; contains no forbidden adverb
      (*provably, automatically, seamlessly, trustlessly, safely, correctly,
      completely*) — mechanically grep-checkable.
- [ ] Demo link present under thesis, resolves (no 404; pre-demo-page target is
      the README anchor).
- [ ] Topology artifact exists with ≥6 named edges, each edge a conversion claim
      in lexicon register (evidentiary, not law-enforcement metaphor — per
      constellation-lexicon).
- [ ] ≥6 components rendered in the five-field skeleton; every "what it refuses"
      cell non-empty; ≥1 component shows a real receipt id that exists in a
      public repo.
- [ ] "Agent Governor" is not the page title, h1, or umbrella term anywhere.
- [ ] Page remains a single static HTML file (or +1 for topology.html), no
      build system introduced, existing aesthetic preserved (CSS vars, fonts,
      dark mode intact).
- [ ] Existing shelves/research/writing content still reachable.
- [ ] Works with no JavaScript (diagram may degrade, must not vanish).

## Non-goals

- No microsite sprawl; no new domains. `agent-governor-site` fold-in is DNS-level
  (operator action, open question below) — this spec does not touch it beyond not
  linking to it.
- No live demo execution on the site; the site points at reproducible local
  commands. No backend, no analytics, no framework.
- No completeness: organs that are zoned render as `zoned` stubs. Dumb but
  structurally right is the bar; polish is item 4's problem.

## Open questions (operator)

1. `agent-governor-site` — retire CNAME with a redirect, or leave parked until
   after launch? (Either is fine for this spec; hub must not link it.)
2. Does the topology render as a section of index.html or a separate
   `topology.html`? Spec default: separate page only if index exceeds ~900
   lines; otherwise section.
3. neutral.zone cross-link placement: footer (spec default) or header?
