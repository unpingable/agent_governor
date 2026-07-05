# Campaign: Constellation Public MVP — "First Visitors"

> **Ratified 2026-07-05** (operator plan approval). Live progress + reality
> corrections live in `STATUS.md` — notably: Sprint 1 found the "13 unpushed AG
> commits", "uncommitted maude fix", and "porter is design-only" claims below
> were STALE (all three resolved better than surveyed; porter had working code
> + tests). The card is preserved as ratified; STATUS corrects.
>
> Maude-ready iterative plan to get the constellation ready for public use.
> Planner output — NOT authority. All admission/promotion/minting = Human/Governor.
> Discovery basis: 3 survey agents + direct checks, 2026-07-05. Operator rulings
> this session: constellation = repos named in AG docs (incl. NQ, Nightshift,
> Porter, Standing, LA, Wicket, Spine, Continuity, Lean, Verifier); "Someone"
> excluded; **NQ featured openly** (Option B: document AG's dependency on its
> witness contract) and **featured as the flagship "usable today by normal SREs"
> organ**; **install-from-source** stays the stance (no PyPI in MVP);
> **newlean is not relevant — dropped**; and a campaign-scoped posture ruling:
> **YAGNI / forcing-case fences do NOT gate public-readiness work here.** If a
> tool needs building to be public (e.g. Spine), plan it, blueprint it, build
> it — publicization is definitional scope for this campaign, not speculative
> expansion. (Authority fences — arming C11, live cage, minting — still hold;
> the ruling cuts process red tape, not custody.)
> **UI ruling (operator, 2026-07-05):** besides maude — **gov-webui** is brought
> up to date AND gains a maude-equivalent operator mode (keeping legacy modes);
> **vscode-governor / clerk** = planner's judgment (taken: vscode-governor gets
> a cheap compat+smoke packet; clerk PARKED for MVP — three concurrently-current
> operator surfaces is over-claim risk); **guvnah ignored** (retired).
> **Push window:** today is Sunday — Sprint 1 pushes may execute immediately.

---

## 1. MVP claim

**"You can watch an AI agent's work enter a governed pipeline as a *candidate*,
see the system refuse what it cannot verify, and inspect the receipts for both."**

An external person with a laptop can, in under 30 minutes:

1. **Understand** what the constellation is from one public page: language is a
   proposal, not an authority; agent work enters as candidate work; nothing
   converts to relied-upon authority without standing + receipts.
2. **Run or inspect a minimal governed workflow**: live (`pip install -e .` →
   `demo/refused-spend.sh` → `demo/interrogate.sh`; optionally Maude supervised
   run) — or offline, via a checked-in self-verifiable specimen corpus
   (the CD-4B pattern: queue.json, approval witness, ReviewPacket, receipts).
3. **See refusal as a first-class outcome**: a refusal gallery where each organ
   refuses in 30 seconds and the receipt says exactly why (AG temporal lapse,
   Nightshift stale witness, Wicket laundering fixture, Continuity rely-gate,
   Porter unobserved-exit, NQ cannot-testify).
4. **See what is deliberately not granted to agents**: a written non-grant list
   backed by pointers to enforcing code and pinning tests.

The MVP is **legibility + inspectability + one live path** — not hosted service,
not multi-provider coverage, not the full 60-module surface.

## 2. Non-claims

- NOT a hosted service, SaaS, or anything with uptime obligations.
- NOT "the constellation is production-hardened." Only the demo path is
  warranted, at its stated custody grade (versioning-by-custody-grade: the major
  digit is an authority claim). Bootstrap limits stay documented: in-process
  custody forgeability, operator-fiat standing, C11/seccomp unarmed.
- NOT live agent execution in a cage. v0 refuses live by construction; that
  refusal is presented as a feature of honesty, not hidden as a roadmap gap.
- NOT PyPI/packaged distribution (deliberate; README already says so).
- NOT "self-improving agents" / agent-swarm marketing (compound-harness
  vocabulary deliberately burned). Agents talk to the ledger; the public story
  says so plainly.
- NOT provider breadth: `claude_code` is the only live supervised backend
  (gemini defunct; Antigravity probe-only). The provider *contract* is public;
  conformance is claimed for exactly one provider.
- NOT a claim that every sibling edge is wired. governor-atlas's wired/specified
  split is part of the public story ("resolved ≠ supported").
- NOT a bundled stack: no organ is a hard requirement for another. AG works
  without NQ (witness seam degrades to honest absence, never fails open);
  compositions like NQ→Nightshift→AG are illustrative lanes, not prerequisites.

## 3. Current-state summary

| Repo | Role | State (2026-07-05) | MVP verdict | Biggest gap |
|---|---|---|---|---|
| **agent_gov** | Admissibility kernel, receipts, refusal, interop contracts | 2.8.1-alpha, ~14.6k tests green, demo path GREEN from fresh clone; 4 interop contracts DRAFT + 4 JSON schemas; **13 commits unpushed** | READY core; hygiene + runbook needed | No stranger-tested "smallest governed workflow" guide; contracts unratified |
| **maude** | Operator shell / run review | v2.4.0 pushed, 282 tests; supervised loop + promotion review + desk screens + M-2 plan ingestion all work | **READY** | M-4 run report stub; CD-4B harness fix uncommitted; live-daemon smoke |
| **nq** | Witness / substrate testimony / cannot-testify | Public GitHub, Apache-2.0, 1203 tests, 15+ operator docs; operator: "near usable by normal SRE types" | **READY — FLAGSHIP** (feature prominently) | AG↔NQ relationship (optional!) undocumented publicly |
| **nightshift** | Deferred agent work w/ receipts + governed promotion | Pushed; README leads with runnable stale-witness refusal specimen; **less built than NQ** (operator calibration 2026-07-05) | READY as *specimen*, not as product claim | Story must not imply maturity parity with NQ |
| **porter** | Substrate courier (ssh/serial/recipe cages), custody of execution | **Design-only: zero commits**; charter + record.v0 ratified in docs | INCLUDE (operator ruled); needs impl sprint | Entire implementation + tests |
| **standing** | Workload identity / standing receipts | Pushed, specimen flow runs; Phase 5 hardening | READY | HMAC-only identity substrate (named limit) |
| **linearaccountant** | Conserved capacity/spend ("Scrooge") | Pushed; "frozen as a reference boundary" | READY as reference seam, not product | No transport (by design until consumer trigger) |
| **wicket** | Single-call admissibility preflight | Pushed; SPEC v0.3; 21 fixtures; wicket-guard absorbed | **READY** | Remote-standing seam (AG bridges) |
| **continuity** | Governed cross-session memory (MCP) | Pushed, 32 test files; observe→commit→rely w/ receipts | **READY** | Reliance policy semantics permissive |
| **lean** | Formal admissibility kernels | v7.0.0, sorry-free, Zenodo DOI; [1.0]/annex/scratch tiers | **READY** | newlean BoundedCalculi merge pending |
| **verifier** | Z3 boundary checker measurement→claim | Pushed; lib + CLI + MCP; specimen-at-front README | **READY** | Cross-link only |
| **spine** | Constellation read plane | Charter fixed, "implementation not yet started"; 8 test files, fixtures only | **BUILD** (Sprint S lane — operator ruled: needs-work ≠ deferral) | Core navigable index unbuilt |
| **wicket-guard** | Tombstone | Absorbed into wicket | ARCHIVE (done) | Redirect README exists |
| **gov-webui** | Web operator/chat UI | v0.5.0, GHCR image, README overhauled recently; modes are chat-era | **UPDATE + DESK MODE** (Sprint U — operator directive) | No maude-equivalent operator mode; daemon-surface currency vs 2.8.x unverified |
| **vscode-governor** | Editor surface (CLI-wrapper) | Pinned 2.7.0 vs AG 2.8.1 | SMALL compat+smoke packet | Version drift |
| **clerk** | Electron desktop operator app | Stub daemon pinned 2.7.0; auto-update infra exists | **PARK for MVP** (planner judgment) — map page labels it experimental/parked | Overlaps maude+webui as operator surface |
| **guvnah** | Legacy Electron shell | Retired | IGNORE (operator ruling) | — |
| **unpingable-site** | Public front door | LIVE 2026-07-04 (about/demo/glossary/incident/limits) | READY, needs constellation map page | No single map of all organs |
| **governor-atlas** | AG as receipt-backed claim graph | Live, early, honest wired/specified split | USEFUL, secondary | Most edges "specified" |

**Work triage (phase-3 sort):**
- **Required:** hygiene pushes; porter initial commit; maude fix landing; demo
  stranger-runbook; specimen corpus README; refusal gallery; non-grant list;
  work-container v1 ratification w/ claude_code as first conforming provider;
  Maude M-4; constellation map page; NQ dependency documentation.
- **Useful (in MVP if cheap):** Maude M-3 harness picker; governor-atlas refresh;
  newlean merge; Porter v0.1 implementation (parallel lane).
- **Deferred:** see §6.
- **Obsolete/duplicate:** wicket-guard husk (done right — keep tombstone);
  agent-governor-site (already a redirect — correct); root ROADMAP.md (frozen,
  superseded by docs/roadmaps hub); chat-era maude code (quarantined, GS-15/v3.0).
- **Dangerous:** anything that arms C11/seccomp or live cage dispatch inside
  this campaign; PyPI publication without versioning narrative; publishing a
  ratified contract without the "schema-valid is NEVER admission" language;
  letting Qwen-class output touch a receipt or public claim unverified.
- **Unclear (carry as open questions):** stale project memory says NQ "SECRET"
  (operator ruled public today — memory to be updated after plan approval);
  whether the 5 parked operator rulings (C2 trio, GS-2b HELD, B5, Q-B7)
  intersect MVP (assumed no — none block CD-4 per STATUS).

## 4. Required public-use surfaces

1. **Front door / constellation map** (unpingable-site + `CONSTELLATION.md`
   cross-committed or linked from each repo README): one diagram, one paragraph
   per organ, wired-vs-specified honesty, links. The story: custody stack, AG is
   one organ. **Composition rule (operator, 2026-07-05):** every organ is
   independently usable; the map shows *compositions* (e.g., the monitoring
   lane: NQ witnesses → Nightshift defers/reconciles → AG governs) as
   illustrations, never prerequisites — NQ is NOT a hard requirement to use AG,
   and Nightshift is presented as earlier-stage than NQ.
2. **AG quickstart demo path** (exists): fresh-clone → refused-spend →
   interrogate → opa-contrast, stranger-tested on a clean machine, with a
   TOUR.md narrating what each receipt means.
3. **Smallest end-to-end governed workflow guide**: propose → verify → apply →
   receipts using only local Governor machinery (no Claude Code required) — the
   missing "gap 10" doc.
4. **Governed-work specimen corpus**: CD-4B artifacts curated as the canonical
   inspectable specimen (queue latch, approval witness, plan envelope,
   ReviewPacket, verify-run receipts) + README that walks a stranger through
   verifying the digests themselves.
5. **Maude operator loop**: install → daemon → supervised launch → approve/deny
   → keep/discard; `run <plan.md>` governed-plan path; M-4 run report as the
   human-readable artifact.
6. **Refusal gallery**: one page, six+ 30-second specimens across organs, each
   with the command, the refusal output, and the receipt field that carries the
   reason.
7. **Non-grant list** ("what agents are deliberately not granted"): no
   self-approval (ActorOutputNormalizer), no authority from prose
   (`governance_approval_unverified`), no minting from ALLOW (LA), no
   agent-to-agent coordination (ledger only), no network/write outside ration
   (RationCard locked axes), no unwitnessed clock math (clock_witness), no
   spend past standing horizon (standing_spendability) — each with code + test
   pointers.
8. **NQ flagship placement**: NQ presented first among mature organs as the
   "usable today by normal SREs" entry point (own demo track), with the
   AG-optionality rule intact and Nightshift shown as the earlier-stage
   composition partner.
9. **gov-webui desk mode**: a browser-based maude-equivalent operator mode
   (decision queue, sessions, keep/discard) over the same daemon shell
   contract, with legacy modes kept current — the zero-install-TUI path for
   visitors who won't run a terminal app.
10. **Interop contract v1** (work_container + provider trio): ratified, with
   `claude_code` declared as first conforming provider citing CD-4B
   `sess_aabb2a056f9f` as evidence spine; "schema-valid ≠ admission" language
   preserved verbatim.

## 5. Dependency map

```
S1 Truth-on-disk (hygiene: pushes, maude fix, porter commit, newlean merge)
 ├─→ S2 Stranger path (fresh-clone runbook, TOUR, smallest-workflow guide,
 │        specimen corpus README)          [needs pushed heads to test against]
 ├─→ S3 Refusal gallery + non-grant list + NQ flagship  [needs S1 heads; ∥ S2]
 ├─→ P  Porter v0.1 implementation         [parallel lane; needs porter commit]
 ├─→ S  Spine read-plane v0                [parallel lane; map page must NOT
 │                                          depend on it — static fallback]
 ├─→ U  gov-webui currency + desk mode     [parallel lane; desk mode consumes
 │                                          the SAME shell contract as maude]
 └─→ S4 Contract ratification + Maude M-4  [needs S2 evidence + operator act]
          └─→ S5 Front door + Fable doc-coherence pass (AG standards outward)
                   → reconciliation sweep → launch checklist
                   [needs S2–S4 content; coherence fixes land before sweep]
Operator acts (gating, not sprint work): off-hours pushes; NQ-public memory
update; contract ratification signature; public claim minting at S5 exit.
```

No sprint arms live execution; the cage stays refused-by-construction and the
public story says so (§2).

## 6. Deferred / parked work (explicitly out of MVP)

- **Live cage execution**: C11/seccomp arming, H2 implementation, agy-under-cage
  (S5/AGY-2 gate), WorkContainer→provider live dispatch beyond claude_code.
- **Maude M-5/M-6/M-7** (obstruction-note emission, headless, submit ingress)
  and GS-15 legacy deletion (v3.0 boundary).
- **PyPI packaging** (operator-ruled out of scope) + versioning narrative.
- **LA transport layer** (frozen until consumer trigger — respect the freeze).
- **Standing identity substrate upgrade** (mTLS/OIDC/SPIFFE forcing case).
- **Continuity WLP persistence adapter**; reliance-policy hardening.
- **witness_testimony.v0 decoupling schema** (Option A) — superseded by the
  Option B ruling; file as candidate only if a second witness provider appears.
- **governor-atlas** completeness (edges stay honestly "specified").
- **Parked operator rulings**: C2 read-plane trio, C2 wicket-guard absorption
  follow-through, GS-2b admissibility/HELD, B5 stale-basis + linearity, Q-B7 —
  dependency-ordered, none block MVP.
- **clerk** (Electron operator app) — parked for MVP by planner judgment
  (operator delegated); map page labels it experimental/parked. **guvnah** —
  ignored (retired, operator ruling).
- **9 PARKED.md residents** (cadence, custody, dossier, nlai, receipt_kernel,
  resonance, sorry, thinkulator, wlp) stay parked; the map page may name them
  as parked without describing them.

## 7. Risk register

| # | Risk | Likelihood/Impact | Mitigation |
|---|---|---|---|
| R1 | **Unpushed work is a disk-SPOF** (13 AG commits; porter entirely untracked; maude fix uncommitted) | Med/High | Sprint 1 is exactly this; operator pushes off-hours per push-timing rule |
| R2 | **Contract-ratification laundering**: public readers read schema-validity as admission | Med/High | "Schema-valid is NEVER admission" survives verbatim in every published contract + gallery; codex adversarial pass on all public contract text |
| R3 | **Demo rot**: demo path breaks silently after later changes | Med/Med | Fresh-clone smoke (`@smoke` marker exists) extended to run the three demo scripts; verify-run receipts required per release-ish tag |
| R4 | **Over-claiming custody grade** in public wording | Med/High | Versioning-by-custody-grade pin; Fable reconciliation sweep in S5 hunts grade inflation; limits.html stays load-bearing |
| R5 | **Qwen-output laundering** into receipts/claims | Med/Med | Routing rule: Qwen output is testimony-grade; every packet names a non-Qwen verifier; nothing Qwen-authored merges without a re-derivation |
| R6 | **Maude live-daemon drift**: desk screens verified offline only | Med/Med | S2 includes one live-daemon smoke session with receipts |
| R7 | **Porter scope creep** (courier → CI tool) | Low/Med | DESIGN.md non-goals are the packet's stop condition; no domain vocabulary in outcome, pinned by test |
| R8 | **NQ memory conflict** resurfaces (stale "SECRET" label) | Low/Med | Update project memory + PROVENANCE cross-note in S1; ruling recorded here |
| R9 | **Sprint sprawl** — campaign becomes platform work | Med/Med | Each packet has stop condition; anything new-surface goes to candidates/, not the sprint |
| R10 | **Single-operator bottleneck** on ratification/pushes | High/Low | Batch operator acts at sprint boundaries; list them explicitly in each packet |

## 8. Model / work routing strategy

(tick=moves cargo; tock=cheapest model satisfying the gap; Fable for conceptual seams)

| Class | Use for | Never for |
|---|---|---|
| **Fable** | Campaign planning, cross-repo reconciliation, contradiction finding between repo claims, final public-story synthesis, MVP-claim wording | Bulk mechanical edits; authority decisions |
| **Opus-class** | Architecture-sensitive edits (daemon RPC, admission seams, work_container_bridge, Porter transport core), hard adversarial review at HIGH checkpoints, fail-closed harness fixes | Doc normalization, checklist grinding |
| **Sonnet-class** | Bounded coding to a spec, README/TOUR drafting to template, tests against pinned behavior, specimen curation, mechanical refactors, Porter CLI plumbing | Changing a refusal class, receipt schema, or authority seam |
| **Local Qwen-class** | Grep summaries, issue clustering, transcript digestion (CD-4B drive log → M-4 fuel), draft checklists, link checking, first-pass "does this README parse to a stranger" reads | ANY load-bearing claim; anything pasted into a receipt/contract/public claim without a stronger reviewer re-deriving it |
| **Human/Governor** | Queue latch, plan promotion, approval witnesses, ratification, pushes, repo-visibility decisions, public claim minting | — |

Standing rules: (a) actor never greens its own gate — every packet names an
independent verifier; (b) authority-seam packets get the codex/Opus adversarial
sandwich (it caught approval-by-narration in CD-1a); (c) all test verdicts via
`governor verify-run` (masked-exit guard), receipts retained; (d) Qwen work is
always paired with a mechanical check or Sonnet re-derivation.

## 9. Maude sprint queue

Sprint = a Maude-sized batch: 4–8 packets, each independently reviewable,
each closing with receipts. Operator acts listed per sprint, batched at exit.

### Sprint 1 — "Truth on disk" (hygiene; full detail in §10)
Push/land everything that exists only locally; make repo state match the story
we're about to tell. Exit: every constellation repo's public HEAD contains the
work the MVP will cite. Operator acts: off-hours pushes; NQ memory correction.

### Sprint 2 — "Stranger path"
1. **Fresh-clone demo verification** (agent_gov) — Sonnet, clean container:
   clone → install → 3 demo scripts; artifacts: run transcript + verify-run
   receipts; verifier: mechanical (exit codes) + Opus spot-read; stop: any
   deviation from README = obstruction note, don't fix inline.
2. **TOUR.md** (agent_gov `docs/`) — Sonnet draft from the run transcript, Qwen
   first-pass stranger-read, Fable final read; receipt: doc registered via
   `governor doc register`; candidate-only until S5 mint.
3. **Smallest-governed-workflow guide** (agent_gov) — Sonnet: propose→verify→
   apply→receipts with zero external agent; checks: every command executed via
   verify-run in a fresh init; verifier: Opus (accuracy of authority language).
4. **Specimen corpus README** (agent_gov `specimens/`) — Sonnet + Qwen digest of
   CD4B_DRIVE.md; walks digest re-verification by hand; verifier: mechanical
   re-hash script + codex pass (no narration-as-authority).
5. **Maude live-daemon smoke** (maude) — Opus-class, one supervised session
   against a live daemon exercising queue/board/adapters screens; artifacts:
   event log + session receipts; stop: any RPC contract mismatch → obstruction,
   file against GS backlog, do not patch daemon in this lane.

### Sprint 3 — "Refusal gallery + non-grant list"
6. **Refusal specimen collection** — Qwen sweep of each repo's README/tests for
   its 30-second refusal (AG temporal-lapse, Nightshift stale-witness, Wicket
   laundering fixture, Continuity rely-refusal, Standing expired-grant, NQ
   cannot-testify, Porter refused-exit [lands when P-lane does]); output:
   candidate list with commands; verifier: Sonnet re-runs each command,
   verify-run receipts attached.
7. **Gallery page** (unpingable-site or agent_gov docs) — Sonnet; each entry =
   command + refusal output + receipt field carrying the reason; Fable pass for
   story coherence; candidate until S5.
8. **Non-grant list** (agent_gov `docs/`) — Sonnet drafts from §4.7 skeleton;
   every line gets a `file:line` + pinning-test pointer; verifier: Opus checks
   each pointer actually enforces the claim (this is the highest-laundering-risk
   doc in the MVP → codex sandwich mandatory).
9. **NQ relationship note** (agent_gov PROVENANCE/docs + nq cross-link) — Sonnet;
   documents Option B (FindingSnapshot consumption, origin_mode vocabulary) with
   the operator's framing pinned: **NQ is an optional witness input, never a
   hard requirement to use AG** — AG runs standalone; absent NQ, the witness
   seam yields honest absence/cannot-testify, never fails open. Also names the
   ops pipeline lane (NQ witness → Nightshift deferred work → AG governance) as
   one *illustrative* composition, with Nightshift marked earlier-stage than NQ.
   Verifier: Qwen link-check + operator read (touches multiple repos' public
   story); codex pass on the optionality language (highest misread risk:
   "constellation" ≠ "required stack").
9b. **NQ flagship placement** — Sonnet: run NQ's quickstart as a stranger
   (cargo build → witness → monitor → one refusal/cannot-testify moment),
   verify-run receipts; fix-list any friction back to NQ's lane; map page and
   demo script place NQ first among mature organs ("usable today by normal
   SRE types" — operator calibration 2026-07-05). Verifier: mechanical +
   operator read.

### Sprint P — "Porter v0.1" (parallel lane, Sprints 2–4)
10. **Initial commit + license year** (porter) — mechanical (S1 packet, listed
    here for lineage).
11. **Transport core: ssh + recipe substrates** — Opus-class (exit-code custody
    is fail-closed logic); tests with mocked transports; stop: serial-socket may
    slip to v0.2.
12. **record.v0 assembly + outcome discipline** — Sonnet with Opus review; pin
    test: outcome vocabulary contains NO domain words (`success/passed/
    admissible` absent) and `exit_code_observed=false` ⇒ `refused`.
13. **Porter README quickstart verification** — Qwen stranger-read + Sonnet run
    against a local ssh target; verify-run receipts.
    AG-side note: AGY-2 seam already consumes `porter.record.v0` fail-closed —
    an integration test against a REAL porter record replaces the synthetic
    fixture when P-lane lands (small AG packet, Sonnet).

### Sprint S — "Spine read-plane v0" (parallel lane, Sprints 2–5)
Operator ruling: needs-work ≠ deferral. Spine's charter is fixed ("read plane,
not authority plane; findability is not legitimacy"); build the smallest
public-usable index.
S1. **Blueprint + skeleton confirmation** (spine) — Opus-class: pin the stack
    (Python/pyproject already present; declare it — kill the "build system TBD"
    line), write the v0 index design note (input = a *declared* corpus manifest,
    output = navigable index artifact + non-authority render); operator ratifies
    the one-pager. Stop: design note committed; no authority verbs added.
S2. **Navigable index v0** — Opus core + Sonnet fixtures: ingest a real declared
    corpus (agent_gov docs/roadmaps + campaign docs as the specimen corpus),
    emit the index; the existing pins stay green (`test_render_non_authority`,
    manifest contract, edition diff). Verifier: mechanical + codex pass that no
    output field implies endorsement/status.
S3. **30-second specimen + README refresh** — Sonnet; README gets the runnable
    specimen at front; Qwen stranger-read; verify-run receipt.
S4. **Map-page wiring note** — the constellation map *may* cite spine's index as
    "how to browse the corpus" but must not depend on it (static fallback);
    candidate-only until S-lane lands.

### Sprint U — "gov-webui desk mode" (parallel lane, Sprints 3–5)
Operator directive: bring gov-webui current + add a maude-equivalent operator
mode, keeping legacy chat modes.
U1. **Currency audit** (gov-webui) — Sonnet: run against a live AG 2.8.x daemon;
    inventory which existing endpoints/modes still work vs broke; Qwen digests
    the delta into a fix list. Verifier: mechanical (contract tests exist in
    agent_gov integration/ — reuse them).
U2. **Legacy-mode repairs** — Sonnet, bounded to the U1 fix list; no new
    surfaces. Stop: legacy modes green against 2.8.x.
U3. **Desk mode v0** — Opus-class lead: the maude-equivalent operator mode over
    the SAME wire surface maude uses (`operator.decisions.list/watch/resolve`,
    `runtime.session.*`, `runtime.promotion.*` — the shell contract; consider
    consuming `libs/ag_shell_client` semantics so webui and maude can't drift).
    Scope v0: decision queue (approve/deny), sessions board, promotion
    keep/discard, governed-plan run status. NOT in v0: plan authoring, M-4
    report parity. Verifier: codex pass on the one-mutation-door rule (resolve
    is the only write path; no privilege escalation via forged args) +
    live-daemon smoke with receipts.
U4. **README/screenshots refresh** — Sonnet + Qwen stranger-read; map page
    entry. Candidate until S5 mint.
U5. **vscode-governor compat packet** — Sonnet: bump/verify against AG 2.8.x
    (`governor check` CLI contract), run its smoke, fix trivial drift only;
    anything structural → obstruction note, post-MVP. Clerk: PARKED — one-line
    map-page label, no code work (revisit post-MVP if webui desk mode proves
    the demand).

### Sprint 4 — "Contract v1 + Maude M-4"
14. **Work-container contract ratification package** (agent_gov) — Fable
    assembles the ratification memo: DRAFT→v1 diff, claude_code as first
    conforming provider, CD-4B `sess_aabb2a056f9f` evidence chain, invariant
    language checklist; **operator act: ratify**; codex adversarial pass first.
15. **Maude M-4 run report** (maude) — Opus-class: compose ReportScreen from
    existing reads on session end; render ReviewPacket "precise law underneath,
    ordinary work language on top"; tests extend the 282-suite; verifier:
    operator dogfood read of a CD-4B-shaped report.
16. **Maude M-3 harness picker** (maude, stretch) — Sonnet: replace hardcoded
    `claude_code` with `runtime.adapters.list` selection; drop if sprint runs
    long (post-MVP acceptable).
17. **Land the uncommitted maude harness fix** — done in S1; M-4 depends on it.

### Sprint 5 — "Front door + reconciliation + launch"
18. **Constellation map page** (unpingable-site) — Sonnet draft, Fable
    story-pass; one diagram, per-organ paragraph, wired/specified honesty,
    parked list named.
19. **Per-repo README cross-links** — Qwen proposes, Sonnet applies (one
    paragraph + link per repo; no vocabulary imports across repos — local
    grammar rule).
20. **Constellation doc coherence pass** — **Fable job** (operator-requested;
    complexity warrants it): one editorial pass across every public-facing doc
    set to make the whole constellation read as one coherent body. **AG holds
    most of the standards-work already** (lexicon, roadmap/ROUTING discipline,
    receipt vocabulary, wired/specified split, candidate/landed markers) — the
    pass propagates AG's standards *outward* as the reference idiom rather than
    inventing a new style, while respecting each repo's local grammar (share
    conventions and markers, not vocabulary imports). Scope: README shape
    (specimen-at-front), status-marker consistency, term definitions before
    use, cross-link topology, tone. Output: per-repo fix lists → Sonnet
    applier packets; Fable never applies its own edits (actor/gate split).
20b. **Fable reconciliation sweep** — contradiction hunt across all public
    text: grade inflation, admission-language leaks, stale claims (e.g.,
    anything still calling gemini live); output: contradiction list → fix
    packets or obstruction notes. Runs AFTER 20's fixes land.
21. **Launch checklist + DoD walk** (§14) — Fable compiles; **operator acts:
    final pushes, public claim minting, site deploy**.
22. **Demo screencast/script final** (§13) — Sonnet; optional recording is
    operator's call.

## 10. First sprint packet in full detail — Sprint 1 "Truth on disk"

**Sprint goal:** every artifact the MVP will cite exists on a pushed public
HEAD; no story is told about bits that live on one disk.
**Sprint stop condition:** all packets closed or obstructed; no new surfaces
opened; nothing armed.

### Packet 1.1 — Push AG's local commits
- **Repo:** agent_gov · **Purpose:** eliminate the 13-commit disk-SPOF
  (S6–S7, H1 cage slice, review chain, bwrap backend).
- **Input context:** `git log origin/main..main --oneline`; REENTRY.md push-state
  note.
- **Worker class:** Human/Governor (push is an operator act; push off-hours per
  standing rule). Sonnet may pre-verify: full suite green via
  `governor verify-run -- pytest tests/` before push.
- **Maude packet shape:** operator decision card — "verify-run receipt attached;
  push authorized?"
- **Expected artifacts:** pushed origin/main; verify-run receipt (pre-push
  suite).
- **Tests/checks:** full pytest suite; ruff clean.
- **Verifier:** mechanical (exit codes); no model verdict involved.
- **Receipt requirements:** verify-run receipt ID recorded in campaign STATUS.
- **Stop condition:** push completes; origin/main == local main.
- **Obstruction behavior:** if suite is red → halt packet, file the failure,
  do NOT push; if push rejected (diverged remote) → obstruction note, operator
  resolves.
- **Candidate-only:** nothing — this mints no claims; pushed ≠ canonical (custody
  ladder).
- **MVP relevance:** every later citation of playbooks/conveyor code requires a
  public HEAD.

### Packet 1.2 — Land the maude allow_dirty harness fix
- **Repo:** maude · **Purpose:** the CD-4B fix (governed-plan launch threads
  `allow_dirty=True` with Tock-2 baseline fence) is uncommitted; M-4 and every
  future governed-plan run depend on it.
- **Input context:** uncommitted diff on maude main; STATUS.md CD-4 entry;
  the +2 tests.
- **Worker class:** Sonnet (commit prep, message, test confirmation) +
  Human push.
- **Maude packet shape:** review packet — diff + test receipt + proposed commit
  message; operator keep/discard.
- **Expected artifacts:** commit on maude main; suite receipt (281+2 expected
  pass / 24 skip).
- **Tests/checks:** `governor verify-run -- pytest` in maude; ruff.
- **Verifier:** mechanical + Opus one-pass on the fail-closed reasoning (the fix
  touches launch gating — confirm dirty-tree refusal still default; only
  governed-plan path threads the flag).
- **Receipt requirements:** verify-run receipt; the Opus review verdict noted in
  commit body or campaign STATUS.
- **Stop condition:** committed + pushed; suite green.
- **Obstruction behavior:** if the fix weakens default fail-closed launch →
  BLOCK, redesign in maude's lane, not this campaign.
- **Candidate-only:** n/a (routine implementation; not custody-affecting).
- **MVP relevance:** without it, `run <plan.md>` refuses after any specimen flip
  — the demo path dies.

### Packet 1.3 — Porter initial commit
- **Repo:** porter · **Purpose:** the courier's ratified design exists only as
  untracked files; commit + push so the P-lane has a base and the design is
  citable.
- **Input context:** README/DESIGN/CANDIDATE/PROVENANCE/LICENSE/porterlib
  skeleton; LICENSE `{{YEAR}}` placeholder.
- **Worker class:** Sonnet (fix LICENSE year → 2026, sanity-order files, initial
  commit) + Human push.
- **Maude packet shape:** review packet — file listing + LICENSE diff; operator
  keep/discard.
- **Expected artifacts:** porter main @ initial commit, pushed.
- **Tests/checks:** none yet (no code); `git status` clean after commit.
- **Verifier:** Qwen file-inventory read (nothing secret/stray in the tree —
  outputs/, __pycache__ excluded via .gitignore) + operator glance.
- **Receipt requirements:** commit hash recorded in campaign STATUS.
- **Stop condition:** pushed; .gitignore excludes outputs/ + __pycache__.
- **Obstruction behavior:** stray private material found in tree → halt, operator
  triages.
- **Candidate-only:** DESIGN stays v0/candidate; committing ≠ ratifying the
  record schema for external consumers.
- **MVP relevance:** operator ruled Porter in; nothing can cite an untracked
  design.

### Packet 1.4 — NQ posture reconciliation
- **Repo:** agent_gov memory + docs · **Purpose:** record today's operator
  ruling (NQ featured openly, Option B) where future sessions will find it;
  kill the stale "SECRET" label.
- **Input context:** this campaign doc §Scope; memory file
  `nq_governor_steals.md`; survey-2 findings.
- **Worker class:** Sonnet (memory edit + one-line PROVENANCE cross-note stub
  for the S3 dependency-note packet).
- **Maude packet shape:** doc diff card.
- **Expected artifacts:** updated memory file + MEMORY.md line; breadcrumb in
  campaign STATUS.
- **Tests/checks:** n/a (docs).
- **Verifier:** operator read (visibility rulings are operator-owned).
- **Receipt requirements:** none beyond the diff (memory is not a receipt
  surface).
- **Stop condition:** memory no longer asserts secrecy; ruling + date recorded.
- **Obstruction behavior:** if operator wants to re-open the ruling → halt, this
  is their decision alone.
- **Candidate-only:** the *public* dependency note itself waits for S3 packet 9.
- **MVP relevance:** prevents a future session from re-hiding a featured organ.

### Packet 1.5 — Campaign card + STATUS file
- **Repo:** agent_gov `docs/campaigns/public-mvp/` · **Purpose:** campaign-card
  discipline — card before slice 1, exit tickets per slice, two-verdict close
  (cargo AND dogfood).
- **Input context:** this plan document.
- **Worker class:** Sonnet (transcribe §1–§9 into CAMPAIGN.md + STATUS.md in
  repo idiom).
- **Maude packet shape:** doc-create card.
- **Expected artifacts:** CAMPAIGN.md, STATUS.md (receipt columns per sprint).
- **Tests/checks:** doc registered (`governor doc register`) if doc-governance
  is in use for campaigns.
- **Verifier:** Fable one-pass (fidelity to this plan; no silent scope adds).
- **Receipt requirements:** doc-registration receipt if applicable.
- **Stop condition:** files exist on a branch/main per repo convention.
- **Obstruction behavior:** conflicts with an existing campaign naming → file
  under existing hub conventions instead; don't fork conventions.
- **Candidate-only:** entire campaign is candidate until operator opens it.
- **MVP relevance:** it's the spine every later packet reports into.

**Sprint 1 exit ticket:** all five packets closed/obstructed; pushed HEADs
recorded; verify-run receipt IDs listed in STATUS; operator has batch-executed
the push set off-hours; two-verdict note (cargo: bits public; dogfood: did the
packet shapes work in Maude?).

## 11. Prompts for worker agents (templates)

**Qwen-class (recall/digest — testimony only):**
> You are a non-authoritative digester. Task: {e.g., "list every refusal-demo
> command in these READMEs with the exact command and expected failure text"}.
> Rules: quote verbatim with file paths; never paraphrase authority language
> (refuse/admit/verify/ratify); if you cannot find something, say NOT FOUND —
> do not infer. Output: markdown list, one item per finding, path + line. Your
> output is testimony; a stronger reviewer re-derives anything load-bearing.

**Sonnet-class (bounded build/doc):**
> Implement exactly the packet below. {packet fields}. Constraints: do not
> touch refusal classes, receipt schemas, or authority seams; if the task seems
> to require it, STOP and emit an obstruction note instead. All test runs via
> `governor verify-run -- <cmd>`; attach receipt IDs. Match surrounding idiom.
> Deliverable: diff + receipts + a 5-line summary distinguishing what you
> VERIFIED (ran) from what you BELIEVE (read).

**Opus-class (architecture edit / hard review):**
> {packet}. You are editing a fail-closed seam. Before the diff: name the
> invariant the seam enforces and the test that pins it. After: show the pin
> still holds (verify-run receipt). If your change would convert any refusal
> path into a warning or default-open, STOP — that is a redesign, not a packet.

**Fable (reconciliation):**
> Sweep {docs set} for contradictions with repo reality as of {HEADs}: custody
> grade inflation, admission language applied to testimony, stale provider
> claims, vocabulary imports across repo grammars. Output: numbered
> contradiction list, each with both sources quoted, proposed disposition
> (fix-packet / obstruction / operator question). Do not fix anything yourself.

## 12. Verifier prompts

**Codex/Opus adversarial (authority-seam sandwich):**
> Refute this packet's claim: "{claim, e.g., every non-grant list line is
> enforced by the cited code+test}". Attack modes: (1) pointer exists but
> doesn't enforce the sentence as written; (2) enforcement is default-open on
> any path; (3) the sentence claims live authority where evidence is
> lab/synthetic; (4) narration-as-authority (a doc says "approved/verified"
> with no independent witness). Report: file:line per finding, <400 words,
> verdict PASS/BLOCK. Default to BLOCK when uncertain.

**Mechanical verifier (every packet):** the tested command's exit code is the
verdict — `governor verify-run -- <suite>`; a green with `masked_exit_risk:
true` or no verifier receipt is refused at AUDIT (loop-protocol §3).

**Stranger-read verifier (docs):**
> Read as an outsider with no constellation vocabulary. Flag every term used
> before it is defined, every step you could not execute literally, every
> claim you'd have to take on faith. Output: ordered list with quoted text.
> (Qwen may run this pass; a Sonnet must confirm the fix list.)

## 13. Public demo script

**Track A — inspect only (no install, ~10 min):** front-door map page → refusal
gallery (read three specimens) → specimen corpus on GitHub: open
`specimens/cd4-docs-normalize/`, follow README to re-verify one digest by hand
→ non-grant list → limits page. Take-away: "refusal is a product surface, and I
could check the receipts myself."

**Track B — run it (~30 min):**
```bash
git clone <agent_gov> && cd agent_gov && pip install -e .
./demo/refused-spend.sh          # Act 1: same credential, t=45 spends, t=51 refused
demo/interrogate.sh <root>       # Act 2: cross-examine the receipts (5 Qs + honest absence)
demo/opa-contrast.sh             # Act 2.5: what a policy engine would have said (allow)
```
Narration beats: two clocks, the gap, the receipt that carries `gap_ns`/`bound_ns`;
"the demo fails loudly if it passes for the wrong reason."

**Track D — SRE lane (~15 min, the flagship "usable today" story):** build/
install NQ → run the quickstart witness+monitor → watch a failure classified by
kind (Δo/Δs/Δg/Δh), then a cannot-testify moment (observability loss witnessed,
not smoothed) → optional composition teaser: Nightshift's stale-witness refusal
specimen (fixture-backed, no live NQ needed; presented as earlier-stage).
Take-away: "monitoring that refuses to pretend, usable by a normal SRE now."

**Track C — operator's chair (~20 min, needs Claude Code):** `governor serve` →
maude → `supervised launch <task>` → approve/deny two tool calls from the queue
screen → keep/discard the diff → (post-S4) open the M-4 run report; then
`run specimens/.../plan.md` and watch admission verify citations before any
execution.

## 14. Definition of done (MVP acceptance criteria)

1. **Fresh-clone truth:** a person on a clean machine completes Track B with
   zero deviations from the published runbook; verified once by a worker and
   once by the operator; verify-run receipts on file.
2. **All cited bits are public:** no MVP doc cites a commit absent from a
   public HEAD (Sprint 1 exit held through launch).
3. **Refusal gallery live** with ≥6 organs, every specimen re-run within the
   launch week (receipts attached).
4. **Non-grant list live**, every line carrying a code+test pointer that
   survived an adversarial BLOCK-hunt.
5. **Contract v1 ratified** by operator with exactly one conforming provider
   (claude_code) and the "schema-valid ≠ admission" language verbatim; DRAFT
   markers removed only by that ratification act.
6. **Maude v2.4.x demo-ready:** supervised loop + governed-plan run + M-4
   report render against a CD-4B-shaped session; live-daemon smoke receipt on
   file.
7. **Porter v0.1** committed, tested, README-runnable for ssh substrate
   (serial may slip), outcome-vocabulary pin test green — or explicitly
   re-scoped by operator to "design-declared" with the map page saying so.
7b. **Spine v0** public: navigable index runs on the declared specimen corpus,
   non-authority pins green, specimen-at-front README — or explicitly
   re-scoped by operator with the map page saying so (static fallback holds).
7c. **NQ featured as flagship**: quickstart stranger-verified with receipts;
   Track D in the demo script; map page places it first among mature organs;
   AG-optionality language intact everywhere NQ is mentioned.
7d. **gov-webui**: legacy modes green against AG 2.8.x AND desk mode v0
   (decision queue + sessions + keep/discard) passes a live-daemon smoke over
   the same shell contract as maude — or operator re-scopes with the map page
   saying so. vscode-governor compat-bumped + smoked; clerk labeled parked.
8. **Front door coherent:** map page + per-repo cross-links deployed; Fable
   reconciliation sweep found zero unresolved grade-inflation or
   admission-language contradictions.
9. **Nothing armed:** C11/seccomp, live cage dispatch, and H2 remain refused/
   unarmed; the limits page says so.
10. **Operator has minted the public claim** — the only step that converts all
    of the above from candidate to public, and it is a human act.

*Two-verdict close:* cargo (the ten criteria above) AND dogfood (did Maude
packet-shapes carry the work without a human becoming the integration layer? —
findings feed the next campaign).

---

## APPENDIX — survey digests (discovery record)

### A. AG public readiness (survey 1)
Runnable today from fresh clone: demo trio green, deterministic, integrity
tripwires. README 29KB, Apache-2.0, py>=3.11, click+rich only, 2.8.1-alpha,
install-from-source, ~14.6k tests. Contracts + schemas all DRAFT/CANDIDATE
("non-binding until ratified AND first conforming implementation"). Live
execution structurally refused v0. Campaigns: conveyor-dogfood CD-4B done;
governed-shell GS-0..8 landed (daemon 91→99); reconciliation HOLDING on A8.
Roadmap hub live (17 active + 9 parked, HEADs verified 2026-07-02); most
sibling edges SPECIFIED not WIRED. Sites: agent-governor-site=redirect;
governor-atlas early-honest; unpingable-site LIVE. Top gaps: no PyPI (ruled
out-of-scope), contracts unratified, no live exec, no conveyor runbook,
13 unpushed commits, no smallest-workflow guide.

### B. Maude / Porter / NQ (survey 2)
Maude READY: v2.4.0 pushed, 282 tests, supervised loop + promotion + desk
screens + M-2 plan ingestion working; M-3/M-4 stubs; GS-15 quarantine OK.
Porter SKELETON: zero commits; record.v0 + non-goals ratified in docs; no
AG/NQ imports (load-bearing); ~2-week impl. NQ: public GitHub, Apache-2.0,
1203 tests, mature docs; exportable vocabulary: origin_mode, cannot-testify,
clock witness, Δo/Δs/Δg/Δh, witness/evaluator split; keep internal: detectors,
schema, transport. Coupling localized to drill_runner/tests.

### C. Siblings (survey 3)
standing READY (specimen flow runs; HMAC-only named limit). linearaccountant
READY-as-reference ("frozen as a reference boundary"; respect the freeze).
spine NEEDS-WORK (charter fixed, index unbuilt) → DEFER. continuity READY
(32 test files, observe→commit→rely receipts; MCP server live). lean READY
(v7.0.0, sorry-free, DOI; [1.0]/annex/scratch tiers). newlean: operator ruled
NOT RELEVANT — dropped from campaign. wicket READY (SPEC v0.3, 21 fixtures,
atemporality pinned). wicket-guard = tombstone, correct as-is.
