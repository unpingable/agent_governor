# RC-0 — Constellation Public MVP, freeze record

> **Frozen 2026-07-05.** Status: **build-complete, unminted.** Authority:
> candidate until the operator ratifies/mints (launch-checklist acts 1–8).
> Scope rule from freeze forward: **no new features** — fixes arising from
> launch acts 4–6 only. ("The dragon is named Scope.")

## Repo state at freeze (all `ahead:0` vs origin — everything cited is public)

| Repo | HEAD | dirty |
|---|---|---|
| agent_gov | `6682632` | clean |
| maude | `3b68a1a` | clean |
| gov-webui | `006bfeb` | clean |
| vscode-governor | `43f283e` | clean |
| porter | `7d4a686` | clean |
| spine | `c435cf4` | clean |
| nq | `b50d8ae` | clean |
| nightshift | `01a65bf` | clean |
| standing | `6413c56` | 1 untracked (`standing.db` — runtime artifact of today's refusal-sweep specimen run; not part of RC) |
| wicket | `939dbb9` | clean |
| continuity | `f868335` | clean |
| verifier | `0155f5c` | clean |
| linearaccountant | `2975500` | clean |
| lean | `84d6d24` | clean |
| unpingable-site | `0eeb973` | clean, **PUSHED** (operator-blessed 2026-07-05; deploy-follow-through is site hosting's concern) |
| governor-atlas | `7ec649d` | clean |

(agent_gov HEAD moves by exactly this freeze-record commit + any launch-act
fixes; the frozen build state is `6682632`.)

## What RC-0 contains (accepted campaign report)

- Campaign card + per-sprint STATUS with receipts: `CAMPAIGN.md`,
  `STATUS.md` (this dir). Sprints 1–5 + lanes P/S/U closed 2026-07-05.
- Public surfaces (all CANDIDATE, adversarially sandwiched):
  `docs/TOUR.md`, `docs/GOVERNED_WORKFLOW.md`, `docs/REFUSAL_GALLERY.md`,
  `docs/NON_GRANTS.md`, `docs/NQ_RELATIONSHIP.md`, `specimens/README.md`,
  `unpingable-site/constellation.html` (+ limits paragraph, positioning
  intro — pushed).
- Ratification memo: `ratification-memo-work-container-v1.md` (artifacts
  bound by digest at `fe560e6`; still byte-identical at freeze).
- Launch path: `launch-checklist.md` (8 operator acts + DoD walk).
- Adversarial record: three real BLOCKs caught and fixed before exposure
  (queue-parser witness mis-attribution; non-grant pointer defects; desk
  door over-claim + proceed-args laundering). The doctrine demonstrated
  itself while building the demo.

## Positioning pin (operator + external review, 2026-07-05)

The public opening is the concrete claim, never the vocabulary:
**"Agents can propose. This shows how to keep them from approving
themselves."** / candidate work in → refusal as a first-class outcome →
receipts inspectable. Refusal is the feature; most demos show success,
this one shows the system saying no and why. Wedge: **AI-assisted ops
work, but reviewable, bounded, receipt-backed** — not "an agent
framework," not constellation-first. First audience: ops/SRE with scar
tissue, security-adjacent engineers, staff+ asked to bless agentic
workflows.

## Open at freeze

- Operator acts 1–8 (`launch-checklist.md`) — incl. the independent 20b
  sweep (re-dispatched at freeze; first attempt died on spend limit).
- Site is pushed; external adversarial passes on the live pages
  (ChatGPT / web-Claude / Gemini / DeepSeek) are now cheap — operator's
  channel.
- Spine OQ-1..5; NQ doc-friction offers; post-launch follow-ups list in
  `launch-checklist.md`.
