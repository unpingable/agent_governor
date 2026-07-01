# Fiction Governor — Consumer Boundary

Status: doctrine (custody boundary for a human-facing domain plugin)
Provenance: relation audit 2026-07-01. Sibling docs: `advisory_vs_constitutional_power.md`,
`standing_and_receipts.md`.

The Fiction Governor is the project's first plausible **human-facing** governor consumer that is
not ops/doctrine scaffolding — a writer may actually use it. That changes what it is. It is not
substrate testimony, not live-cage evidence, not actor admission. It is a **governed use
surface**: a domain plugin whose outputs a human reads and may act on.

The risk here is softer and sneakier than in the ops lane, and therefore worth stating loudly.
Ops laundering wears a hard hat; fiction laundering wears eyeliner and says it's just helping.
The failure mode is a collaborator that quietly takes custody of a human's canon, intent, voice,
taste, or consent.

## The one sentence

> **Fiction Governor may propose, inspect, warn, and stage; only an explicit author act may
> canonize.**

Everything below is that sentence, spelled out.

## What the Fiction Governor MAY claim

- It **verifies** prose/proposals against declared bible + canon and reports pass/fail with
  severity (`VerificationResult`: `success`, `severity ∈ {error, warning, info}`, `suggestions`).
- It **warns** — `NarrativeWarning` is explicitly *"not 'this is wrong' but 'this might need
  justification.'"*
- It **scores/steers** via guardrails (hard constraints C1–C3, soft penalties P1–P4). The
  guardrail invariant is *"user-authored intent fidelity, not morality"* — every hard gate is an
  opt-in unlock keyed to author authorization (`erotic_allowed`, `coercive_play_allowed`,
  `user_signaled_mode`), never a quality or moral judgment. `check()` mutates nothing and blocks
  nothing; it returns a result the caller displays.
- It **proposes** — a `SceneProposal` is a proposal, verified against bible + canon.
- It **stages** — `CanonCaptureClassifier` detects candidate canon facts and returns them as
  `CapturedItem`s hard-set to `CaptureStatus.PENDING` with a determinism `CaptureReceipt`. It
  never writes to canon or bible.

## What the Fiction Governor MUST NOT claim

- It does **not decide canon.** Canon changes only through an explicit author command
  (`canon event add`, `proposal approve <id>`). `Canon.approve_proposal` is a human act, and it
  is a distinct field from `verification_result` — **passed verification is not approval.**
- It does **not impersonate authorial intent.** Suggestions are proposed material, never the
  author's decision.
- It does **not certify prose quality.** Verifiers report constraint conformance, not taste.
- It does **not infer consent from style similarity.** Consent is pairwise, scoped ledger state
  set by the author (`ConsentLedger`), not derived from content.
- It does **not convert generated text into accepted manuscript.** Staging (`PENDING`) is not
  acceptance.
- It does **not make Governor ratification claims** merely because checks passed. It emits no
  gate receipts; its only receipt is a forensic capture-determinism receipt, which attests *what
  was captured*, not *that anyone accepted it*.

## The acceptance boundary (reused vocabulary, not new)

The suggestion→accepted distinction is already first-class in the platform, and the fiction
module already imports the cleanest primitive. No new label is warranted.

| Concern | Existing primitive |
|---|---|
| "generated / staged, not yet blessed" | `CaptureStatus.PENDING → ACCEPTED` (`governor/capture.py`; "no auto-promote, ever") — already re-exported by `fiction_governor/canon_capture.py` |
| "proposed output vs authorizing decision" | `GateReceipt.receipt_role = PROPOSAL` vs `AUTHORITY` (role is part of the receipt hash) |
| the human accepting | `runtime/promotion.py` approve / reject (pending → approved / rejected) |
| "evidence, not authority" | `playbooks/review_packet.py` (`operator_review_required = True`) |

## Direct-to-canon is closed

`scan_manuscript_to_canon` (a library function that wrote regex-extracted events straight into
canon with no confirmation and no provisional marker) was the one laundering vector found in the
audit — dormant (zero callers, zero tests) but real. It was removed 2026-07-01. Manuscript
**extraction** remains available (`ManuscriptScanner`, `scan_single_chapter` → `ScanResult`,
which write nothing); manuscript **ingestion into canon** must go through an explicit author act
or `PENDING` staging. There is no bulk auto-write path, and one must not be re-added.

## Author runbook

A neutral operating envelope for anyone handed this tool:

1. **Declare** the bible (characters / world / tone) and canon (established events) yourself, via
   the `bible …` / `canon …` commands. These are author acts.
2. **Ask** for suggestion, critique, or a scene proposal. Treat *all* output as proposed
   material.
3. **`proposal verify` informs; it does not accept.** Read the delta yourself.
4. **Only `proposal approve <id>`** — your explicit command — updates canon.
5. **Do not bulk-import a manuscript into canon.** If you want the tool to know your existing
   text, use extraction/staging and confirm items one at a time; never let a scan silently
   establish canon.

## Open, non-blocking notes

- **Author fiat is the sovereign override — named non-bug.** `Canon.approve_proposal` accepts a
  `verification_result` it never inspects, so an author may approve an unverified or failed
  proposal. This is correct, not a defect. The intended shape:

  > `VerificationResult` informs author review. Author approval canonizes. Failed or absent
  > verification may be warned, logged, or labeled. It must not block explicit author acceptance
  > unless the project opts into that gate.

  Forcing verify-before-canonize would promote the verifier from **advisor** to **co-authority** —
  the machine could then seize the pen. NLAI forbids that: the machine may say *"this violates
  declared constraints,"* it may not decide the story.

  *Optional future interlock:* projects may require verification before approval, but this is a
  **policy choice, not a custody requirement**. Filed here rather than assumed.
- Nonfiction and Ops governors are the **same consumer class** (governed use surface). The same
  relation audit should run before either goes human-facing.
