# SITE_GAP_DEMO_PAGE_001 — demo page + OPA contrast + Limits page

**Status: spec (build-ready). Launch-order item 4.** Depends on: SITE_GAP_HUB_001
(spine to hang off), `w1-5-opa-contrast-shim` (**done** 2026-06-12 — the contrast
diagram's substance exists as `demo_opa_contrast.py` + receipts).
Backlog: `.governor/backlog/launch-4-demo-page.json`.
Source doctrine: `working/launch-plan-2026-06-11.md` §§The demo / OPA contrast /
Limits page / Show HN gate. Build repo: `~/git/unpingable-site`.

## What exists (all of the page's substance, repo-side, verified live 2026-06-12)

- **The incident:** temporal lapse — standing observed, horizon 10s, spend at
  +11s. Twin passes within horizon. Frozen as golden corpus
  `08-temporal-lapse-refused.json` / `09-temporal-lapse-twin-passes.json`.
- **Act 1 (behavior):** `demo/refused-spend.sh` — twin passes, impostor refused
  with receipt (`refusal_kind=standing_before_spendability_not_bounded`,
  `gap_ns=11e9 > bound_ns=10e9`, named monotonic `gap_basis`). JSON envelope via
  `--format json`. Stranger-gate verified at ~5 min from cold clone (W2 audit).
- **Act 2 (evidence):** `demo/interrogate.sh` — six questions cross-examining
  the same receipts (chain walk, typed reason, failed predicate, clock witness,
  OPA's verdict, honest absence).
- **Act 2.5 (contrast):** `demo/opa-contrast.sh` — OPA correctly allows over the
  unwitnessed input; custody refuses upstream; OPA's verdict itself receipted.
- **Act 3 (necessity):** proof seam — refusal class → Lean class-boundary
  theorem (`Freshness.expired_not_fresh`, clock-agnostic, monotonic
  instantiation recorded; `NO_KERNEL_THEOREM` gaps marked, not borrowed).
- Venv'd reproduce path (README Start Here, live-verified this morning).

**The page is a rendering problem, not a build problem.** Every claim on it must
be backed by one of the artifacts above.

## What needs building

`demo.html` (or `/demo/`) + `limits.html` in `unpingable-site`, same hand-rolled
static grammar as the hub.

1. **One incident, three descents, one page** — vertical structure mirroring the
   plan: Act 1 behavior (the twin passes / the impostor refused — both shown;
   a system that only says no is a brick) → Act 2 evidence (3–4 of the six
   interrogation Q→A pairs, rendered from real transcript) → Act 3 necessity
   (theorem link with the honest-framing sentence verbatim: theorem proves the
   *class boundary*, receipt proves the *instance facts*, the link is the
   artifact). Three descents into one incident, NOT three demos.
2. **The receipt is the hero artifact** — the impostor's refusal receipt
   (corpus 08 / live-run equivalent) rendered as the page's centerpiece: both
   clocks, the gap, the bound, the typed refusal kind, the `gap_basis`. Real
   bytes, syntax-highlighted at most; never a mockup.
3. **Incident legibility in 30 seconds** — a 3-line plain-language summary above
   the fold: *checked at t=40 / horizon t=50 / spent at t=51 — naive auth says
   yes, custody says no, here is the receipt.* (Show HN gate criterion.)
4. **One command to reproduce** — the venv'd clone-to-refusal block, copy-paste
   safe (this morning's README block is the source of truth; the page must not
   fork it — same commands, byte-equal).
5. **OPA contrast diagram** — two lanes, same incident: OPA lane (input document
   → policy → `allow` — "garbage custody in, immaculate verdict out"), custody
   lane (premise preflight → refused upstream, OPA never consulted on
   inadmissible premises → OPA's verdict receipted when it does run). Layering
   sentence verbatim: **policy engines decide over claims; custody systems
   decide whether those claims may become premises.** Static SVG or CSS diagram;
   no live OPA on the site.
6. **Limits page** — the strongest case against, author's voice, exactly the
   plan's sections: what it doesn't prove / what it costs / what must be trusted
   (TCB: locker + sealer + clock authority — "trust with a bill of materials") /
   what happens when witnesses are wrong ("bad with a return address") / what
   conventional tools already do well / where it's the wrong tool / current
   maturity (alpha, solo, research lab not product). Anti-sales line verbatim:
   *If you only need an authorization check, use an authorization check.*
7. **Objection pre-answers** — OPA objection and ai-governance-grift objection
   answered on the demo page or Limits page (one-sentence replies from the
   plan's objection harness; long form can wait).

## Acceptance criteria

- [ ] Demo page shows BOTH outcomes (twin pass + impostor refusal) with real
      artifacts; refusal receipt rendered with `gap_ns`, `bound_ns`,
      `gap_basis`, and `standing_before_spendability_not_bounded` visible.
- [ ] 30-second summary above the fold; a reader who stops there knows what
      happened and why it's not an authorization bug.
- [ ] Reproduce block byte-equal to the README Start Here block (mechanically
      diffable; one source of truth).
- [ ] Act 3 honest-framing sentence present verbatim; the Lean link points at
      the exact theorem, not the repo root. NOT "Lean proved production safe"
      anywhere.
- [ ] OPA diagram: layering sentence verbatim; OPA's lane labeled *correct*
      (the engine is not the villain — its premises are unattested).
- [ ] Limits page: all seven sections non-empty; anti-sales line present;
      zero forbidden adverbs across BOTH pages (grep gate: *provably,
      automatically, seamlessly, trustlessly, safely, correctly, completely*).
- [ ] Every command shown on the pages executed live against the public repo
      state before commit (front-door discipline, same as README ratchet).
- [ ] Hub button (SITE_GAP_HUB_001 item 2) retargeted to this page.
- [ ] Static, no JS required, dark mode intact, no build system.

## Non-goals

- No video, no animation, no interactive sandbox, no hosted execution.
- No OPA-as-supported-surface claims (shim is demo-grade Act 2.5; policy-adapter
  zoo stays dead). No Cedar/admission-controller lanes on the diagram.
- No FAQ page (Limits ≠ FAQ — the plan is explicit). No fourth descent.
- Not the Show HN post itself — that's launch item 6, operator-sequenced, on a
  chosen morning.

## Open questions (operator)

1. Transcript freshness: render from a pinned run (stable, slightly stale) or
   regenerate at build time (fresh, churns the diff)? Spec default: pinned run,
   regenerated only when corpus changes.
2. Does the receipt render link to a downloadable raw JSON copy on the site, or
   only display inline? Spec default: inline + `<details>` raw block, no extra
   file.
3. Limits page tone check is taste — wants one operator read before publish
   (it speaks in the author's voice, which is yours, not mine).
