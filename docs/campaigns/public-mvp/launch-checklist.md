# Launch checklist — public-MVP "First Visitors"

> **STATUS: packet 21 (S5), compiled 2026-07-05.** The DoD walk below is the
> campaign's own accounting; every ☐ that remains is an OPERATOR act or an
> item gated on one. Nothing here mints anything.

## DoD walk (CAMPAIGN §14)

| # | Criterion | State | Evidence |
|---|---|---|---|
| 1 | Fresh-clone truth (Track B) | ☑ worker-verified / **☐ operator run owed** | S2 packet 2.1 (pyyaml fixed `a784364`, all 3 demos exit 0). DoD wants one operator repeat. |
| 2 | All cited bits on public HEADs | ☑ | Every repo pushed today; site cites only pushed AG docs. |
| 3 | Refusal gallery ≥6 organs, run in launch week | ☑ (8 organs, all run 2026-07-05) | `REFUSAL_GALLERY.md` `9f19a23` |
| 4 | Non-grant list survived BLOCK-hunt | ☑ | Opus refute: 4 pointer defects applied, substance held (`9d6e7b4`) |
| 5 | Contract v1 ratified, one conforming provider | **☐ OPERATOR** | Memo `68eae6e` — Option A (graded) recommended |
| 6 | Maude demo-ready (loop + plan + M-4 + live smoke) | ☑ | `receipts-s2-maude-smoke.md`; M-4 `afc2a68`+`704f86b`; suite 301+19 green |
| 7 | Porter v0.1 tested + README-runnable | ☑ | 19 tests; `demo/refused-exit.sh`; ssh real-host caveat honest (`7d4a686`) |
| 7b | Spine v0 public or honestly re-scoped | ☑ (fallback holds) | Engine green (141), docs de-staled; S-B/S-D gated on **☐ OQ-1/OQ-2**; map page says "building" |
| 7c | NQ flagship | ☑ | Stranger run + Track D + map-first + optionality pinned (`bff54d0`) |
| 7d | gov-webui legacy green + desk v0 | ☑ | 533 tests; desk landed `f10e1dd..7e30fbe`; live smoke RUN 2026-07-05: /desk/decisions + /desk/sessions 200 against a real daemon; forged-id resolve refused 404 `decision_not_found` live |
| 8 | Front door coherent; sweep clean | ☑ | Independent 20b sweep ran post-RC-0: 7 findings, all applied (STATUS §20b); clean classes explicit; site PUSHED (`52413b4`) |
| 9 | Nothing armed | ☑ | C11/seccomp/H2/live-cage all refused; limits.html states it |
| 10 | Public claim minted | **☐ OPERATOR** | The one step that converts candidate → public |

## Operator acts, in order

1. **Ratify work-container v1** — memo
   `docs/campaigns/public-mvp/ratification-memo-work-container-v1.md`
   (Option A recommended; edits status lines only; invariant sentences
   untouchable).
2. **Spine OQ-1..OQ-5** — `spine/docs/design/v0-navigable-index.md` §open
   questions (OQ-1 gates packaging, OQ-2 gates the specimen edition; others
   cheap).
3. **Repo-visibility check** — constellation.html links 16 repos at
   github.com/unpingable/*; each must actually be public before deploy
   (mechanical: `for r in …; do curl -s -o /dev/null -w "%{http_code} $r\n" https://github.com/unpingable/$r; done` from any logged-OUT context).
   Known-public: nq, maude, porter (pushed today). UNVERIFIED as public:
   agent_governor itself, lean, standing, wicket, continuity, spine,
   verifier, nightshift, linearaccountant, governor_webui, vscode-governor,
   clerk, governor-atlas. **A 404 on agent_governor kills Track B.**
4. **Operator fresh-clone run** (DoD 1) — 15 minutes, on a machine that
   isn't this one if possible.
5. ~~Desk live smoke~~ **DONE 2026-07-05** — real daemon, feed+sessions
   200, forged-id resolve refused live (404 decision_not_found).
6. ~~20b sweep~~ **DONE 2026-07-05** — independent re-run complete, 7
   findings applied (STATUS §20b); read the summary, nothing left queued.
7. ~~Deploy the site~~ **PUSHED 2026-07-05** (operator-blessed; through
   `52413b4` incl. positioning intro + sweep fixes). Verify hosting picked
   it up, then external adversarial passes on the live URLs are cheap.
8. **Mint** — the public claim, however you phrase it (site live + repos
   linked + this campaign's docs cited). After the mint, DRAFT markers that
   ratification (act 1) cleared may be removed per the memo.

## Follow-ups already queued (post-launch, not gating)

- Desk door unification (route promotion/intervention through the decision
  door) + desk GET/SSE auth posture + UI bearer token — from the F1/F5/F6
  adversarial notes (gov-webui lane).
- Maude M-3 harness picker (deliberately dropped, re-queue).
- NQ doc-friction items 7–10 (coherence-pass list — NQ's lane, offered).
- U4 screenshot refresh (gov-webui); GS-13 overlays (maude); P soft fences
  (F4/F5) stay fenced until forced.

*Two-verdict close (campaign motto): cargo = the table above; dogfood = the
campaign itself ran as governed packet-work — findings on that in STATUS
exit tickets per sprint.*
