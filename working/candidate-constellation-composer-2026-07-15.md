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
