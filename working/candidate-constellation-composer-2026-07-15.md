# Candidate — constellation composer (demo-able specimen, not composer product)

**ID:** `constellation-composer-specimen`
**Filed:** 2026-07-15 (operator: "pencil this in lightly")
**Status:** **CANDIDATE — named, not ratified.** Filing is a handle for
review, not authorization to build. In particular this does NOT amend the
ratified public-mvp campaign envelope; whether it joins the launch DoD is a
separate operator ratification.
**Theory in progress:** `~/git/skunkworks/ux-design/` (codex-authored:
`constellation-composer-witness-ux-2026-07-15.md`,
`IMPLICIT_SCOPE_AUDIT_2026-07-15.md`,
`ux-scope-kernel-throughlines-2026-07-15.md`) — external drafts, candidate
input, no authority.

## The thesis (why this is launch-shaped and not procrastination)

The MVP story today: *"here are several governed components and some
carefully curated demonstrations."* The missing premise: **these tools do
not operate over "the enterprise"; they operate over an explicitly composed
and governed system model** — and that composition currently lives only in
the operator's head and repository doctrine. The audience lacks the
instrument needed to see that the existing tools belong to one system. The
composer is that instrument:

> Here is the system boundary they jointly reason about, and here is how an
> operator declares it.

## The fence (load-bearing)

**Demo-able composer, not composer product.** For MVP it needs exactly:

1. declare a bounded system scope;
2. place components and typed relationships;
3. distinguish observed facts from operator assertions;
4. show authority/evidence/custody boundaries;
5. export a stable machine-readable specimen consumable by one or two
   existing tools;
6. visibly refuse under-specified or contradictory scope.

It does **NOT** need: discovery, reconciliation, live inventory sync, graph
editing worthy of actual CAD, NetBox integration, collaborative state, or a
generalized schema marketplace. That way lies another quarter.

Item 3 is the constellation's own law surfacing in the UI (observed facts vs
operator assertions = testimony vs standing); item 6 is admissibility as UX
(a composer that renders contradictory scope without refusing would be the
first constellation surface to launder). Item 5's export specimen is an
architectural surface (wire format / cross-tool vocabulary) — per YAGNI
scope it gets named early and designed under review, not improvised.

## The demo shape (brutally constrained)

Load one prebuilt "Trek-scale deployment" specimen → alter a boundary or
authority edge → show how NQ/Maude/Nightshift's answers **change — or refuse
to change**. A demo with a thesis, not another dashboard wearing epaulettes.

Guvnah variant of the same beat: load specimen constellation → inspect and
edit one boundary → ratify the change → show downstream consequence/refusal
in another tool.

## The guvnah pivot (candidate identity resolution)

Guvnah becomes **the operator's system-modeling seat**, not another
governor — "a bigger pivot than what I did to maude":

- **Composer declares the system** — components, boundaries, relationships,
  scopes, authority domains.
- **Guvnah is the human-facing chair** where that model is reviewed, edited,
  challenged, and ratified.
- **AG remains execution governance.** **NQ interrogates the declared
  system.** **Maude turns bounded intent into plans against it.**
  **Nightshift operates over the same declared scope after hours.**

The chair's object of work is **the constellation model itself**: *"This is
the owl. These are its edges. These are the parts that count. These are the
claims I'm willing to stand behind."*

**Recorded tension, not resolved here:** Q-A7 (2026-07-02) ruled guvnah v1
RETIRED (specimen only); `guvnah-v2-operators-chair` sits queued post-launch
as a vague console concept. This pivot would re-scope v2 around a concrete
object. Whether that is a v2 re-scope or a fresh surface is an operator
ruling at pickup time; nothing in this filing amends Q-A7.

## Delivery surface — open question (operator noodling, 2026-07-15, same day)

Operator: guvnah "might want to be both app + web (chrome+firefox support) —
right now I think I was focused on app." Plus: "what to do with govwebui and
clerk, if anything" — and, rediscovered mid-thought, the VS Code extension.

**The full human-facing surface inventory** (the operator's own head dropped
one — which is this candidate's thesis demonstrating itself):

| Surface | Substrate | Standing ruling (2026-07-02, `docs/roadmaps/CONSOLIDATION.md`) |
|---|---|---|
| maude | terminal TUI | KEEP — terminal-native operator shell (live, proven by NS-1) |
| gov-webui → **phosphor** | web | KEEP + REFRAME — web-native lane host (ops-casework lane = near-term cockpit) |
| clerk | Electron | parked assistant shell (kept, inactive) |
| guvnah v1 | Electron-ish/stdio | RETIRE (Q-A7 — "premature surface area") |
| vscode-governor | editor extension | separate repo; `docs/CLIENT_ECOSYSTEM.md` narrative STALE (census D3) |

**The substrate question for the seat, unruled:** if the chair wants
app + web, note the constellation already owns (a) a ruled web-native host —
phosphor, where chrome+firefox support is free because it's just the web —
and (b) a parked Electron shell — clerk — that is the obvious app-shell donor
if a desktop app is genuinely needed. Candidate shapes, none ruled:

1. **Seat as a phosphor lane** (web-first; cheapest; both browsers free;
   clerk stays parked; "guvnah" survives as the lane's name or not at all).
2. **Seat as resurrected guvnah app** consuming the same model; web later —
   re-opens Q-A7 and doubles the surface early.
3. **Both as two parallel builds** — the "another quarter" fence says no.
4. **Guvnah as one codebase, two distributions** — web-native core serving
   a webui (chrome+firefox free) AND wrapped in an app shell.
   **← OPERATOR LEAN (2026-07-15, same day; a lean, not a ruling).**
   Distinct from shape 3: this is one surface rendered twice, not two
   surfaces — so it survives the fence IF the core is genuinely web-first
   and the app shell is a wrapper, never a fork. Consequences to rule at
   ratification: (a) **clerk's app-shell-donor role evaporates** — if guvnah
   carries its own shell, clerk's "parked, kept" disposition likely tightens
   toward retirement (operator call; touches the 2026-07-02 consolidation
   table); (b) **phosphor stays purpose-focused on what it does now**
   (operator, same exchange) — web-native lane host, ops-casework lane; the
   seat is a sibling surface, not a phosphor lane, and no shared-hosting
   arrangement is contemplated; (c) the demo-able MVP specimen should ship
   as the WEB rendering first (zero install for the launch audience), app
   shell after — the shell is distribution, not product.

Whatever the ruling, the daemon-authority invariant is unchanged: clients
are views; the composer MODEL and its export specimen are the product, and
they must not care which chrome renders them. Deciding the model/specimen
first makes the substrate question cheap; deciding substrate first makes it
expensive. `CLIENT_ECOSYSTEM.md` (already marked STALE) is where the
eventual ruling should land, not new prose here.

## Gates before any build

1. **Operator ratification** of scope + whether it enters the launch DoD
   (the six-needs list above is the candidate boundary).
2. **Hostile-to-features review of the MVP definition** before slice 1 —
   operator's own warning: "you will enjoy building it far too much."
   Adversarial pass on the SPEC, not just the code.
3. Export-specimen schema named as its own reviewed record (candidate wire
   format; consumers: pick 1–2 of NQ/maude/nightshift, not all).
4. Read-only first; "minimally editable" only if the demo beat requires the
   ratify-a-boundary step.

## Non-binding sequencing sketch

Sits AFTER the current operator remainder (push window, launch acts, NS-2
run) and composes with — possibly replaces the front of — the quarantined
demo-2 arc. It does not gate NS-3..6.
