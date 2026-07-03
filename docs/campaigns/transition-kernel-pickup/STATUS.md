# Status — transition-kernel pickup

As of 2026-07-02 evening (B1 executed; prior snapshots preserved below).

## 2026-07-02 evening — B1 done, Q-B1 resolved, B4 unblocked

- **B1 executed** (INVENTORY §Three worlds): differential green 9/9 EXIT=0;
  corpus enumerated; packet's wicket-verdict map REFUTED (shared vocabulary =
  12-kind refusal enum + 5 seams; corpus is the contract); B5 seed named
  (scope_mismatch, LA token kinds, stale-basis have no cases).
- **Q-B1 RESOLVED BY EVIDENCE**: Standing 1e62ba9/f101c55 already on
  origin/main; the "unpushed" record was stale.
- **B4 = verify-and-adopt**: Slice 1b Steps A+B already committed on
  `feat/transition-kernel-slice-1b` (24acd8f, f003519; 501-line client +
  Office 2 rewire + 453 test lines). Next: run its tests via
  `governor verify-run` (receipted), review, adopt.
- **B2 next** (invariant survival map) — ground truth updated by B1.

## 2026-07-02 — resume (B0 executed)

- Campaign resumed as Packet B of the roadmap program
  (`docs/roadmaps/README.md`); B-series slices added to NEXT.md; Rust-lane
  stop-lines added to CAMPAIGN.md; sign-off questions Q-B1/Q-B3/Q-B4/Q-B7 filed
  in DECISIONS.md.
- **Three-world finding:** the standalone `~/git/transition-kernel` repo (HEAD
  2026-06-18) — Rust Admit/Refuse/Escalate kernel, 9-case byte-conformance vs
  Python via `scripts/differential.py`, summit `stage3b2-first-effect`, Branch A
  Lean feedstock (NoFreeContinuation) authored — was not in the 2026-06-23
  inventory. B1 reconciles it before any Rust work resumes.
- Slice 1b (= **B4**) remains ACTIVE NEXT, gated only by Q-B1 (confirm + push of
  Standing `1e62ba9`/`f101c55`), independent of the reconciliation campaign.

## Done (as of 2026-06-23)

- **Reduction** — verdict B: Standing issues an honest grant-token; the one gap was spend-time
  scope matching. Mint boundary = `activation.py` Office 2.
- **D010 (Model X)** ratified: Standing owns spend-time scope refusal; AG only inherits.
- **Slice 1a** (`~/git/standing`, `1e62ba9`, not pushed): `Store::transition_scoped` refuses
  `ScopeMismatch` non-consuming; Standing now refuses all five load-bearing classes.
- **Transport reduction** — verdict C: Standing's `grant use` was prose-only. Custody finding
  (rule #4): a non-consuming refusal has no transition → no receipt → **D010c asymmetric custody**.
- **D010b/D010c** ratified: the `standing.grant_use.v1` witness packet (success digest required;
  refusal class-only, null digest).
- **Slice 1a-bis** (`~/git/standing`, `f101c55`, not pushed): `grant use --json` emits the v1
  witness packet. **Standing JSON witness is now available** for AG to consume.

## Current next

**Slice 1b — AG adapter** (`activation.py` Office 2): subprocess-invoke `standing grant use
--json`, parse `standing.grant_use.v1`, replace `standing_ok: bool` with the verified result.
Three-way distinction (used / refused / no_verified_result) is load-bearing. See [NEXT.md](NEXT.md).
Open sub-question: how AG locates/invokes the `standing` binary.

## Unpushed (nothing pushed — operator's trigger)

- `~/git/standing`: `1e62ba9` (Slice 1a), `f101c55` (Slice 1a-bis).
- `~/git/agent_gov`: the reduction + D010/D010a/D010b/D010c + capsule commits.

## Not touched (deferred, named)

Supervisor hot-path pickup (`supervisor.py:752` observe-mode self-authorization,
`supervisor.py:433` `fork_session` on prior local approval) — follow-on slices, each with its
own forcing case. Office 2 first. Refusal-witness receipts (Model A) — a separate future
Standing custody campaign.
