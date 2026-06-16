# Next-Session AG Debt Sweep — Parked Plan

> **Disposition 2026-06-16 (recovered into history; SUPERSEDED as an active plan).**
> This 2026-05-18 plan's core sweep already executed that day — see the `DONE
> 2026-05-18` markers below (NLAI status correction `0f2e0c4`, egress wiring
> `53a8367`, the four "no edit needed" specs verified). The candidate it spawned,
> `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md`, is committed in the **same
> recovery sweep** as this file. It is retained as a historical witness — **NOT
> deleted** despite line 125, because the don't-discard-receipts rule wins. It was
> **not** executed by the 2026-06-16 session, which swept a different debt set
> (mcp_safety retirement, operational-authority census, the bootstrap-lab walking
> skeleton). Kept for the negative-result trail, not as live work.

Drafted 2026-05-18 during a debt-survey session before pivoting back to papers / other tools. AG may come back into focus sooner than expected (papers nearly done). This note captures the plan so re-entry doesn't have to re-derive it.

---

## ChatGPT's Suggested Order (user-endorsed, lifted verbatim from session)

1. **Closed/stale gap sweep** — cheap cleanup before architecture
2. **Commit/reclassify the four new 3.x gap specs** if already coherent (mark explicitly as 3.x kernel bucket, not v2 backlog)
3. **~~Wire `chat_bridge` through EgressGate~~ — DONE 2026-05-18 (commit on session-end).** First-order bypass closed for HTTP backends (Ollama, Anthropic). EgressGate is kw-only-required on both constructors; 5 dispatch sites preflight; BLOCK raises `EgressBlocked` before network I/O. 7 regression tests in `tests/test_chat_bridge.py::TestEgressGateWiring`. Gap spec updated with explicit list of what's still open (BackendDestinationProfile registry, provenance-label propagation, dedicated receipt type, subprocess backends, lanes.py cascade, operator-approval flow).
4. **~~Add one regression~~ — DONE 2026-05-18** (7 regressions, not 1)
5. **Leave adapters parked** (Codex / Copilot / OpenCode / Night Shift / local supervisor). Optional: mark each with explicit upstream dependency + next unblock condition. No scaffolding.
6. **Do not touch candidates / proposed v3** (FRAME_CAPTURE_001, DECISION_CONTEXT_001, etc.)

Companion note from ChatGPT worth keeping in view: once `chat_bridge` sends text to a provider, `TEXT_ADMISSIBILITY_GAP` and `SUBSTRATE_CUSTODY` may surface immediately (byte/string decode standing, message irreversibility, disclosure authority, COMMUNICATE as mutation). Right move is still to wire egress first and let those gaps stay named:

> EgressGate governs outbound provider communication. This does not yet settle byte-level text admissibility, disclosure standing, or COMMUNICATE custody. Those remain named gaps.

That sentence probably belongs in the egress-closeout commit message or implementation note.

---

## Step 1 Sweep Findings (7 candidates verified 2026-05-18)

Cross-checked spec status fields against `git log`, `feature-history.md`, and live code under `src/`.

### Cleanly closeable — status field already accurate (4)

No edit needed. These specs already declare `shipped` correctly. They just need to stop counting in the open-debt mental model. The files stay as design rationale.

| Spec | Verification |
|------|--------------|
| `GOV_PRIM_PROV_001` | `src/governor/provenance_labels.py` exists, commit `9efc3e5`, 53 tests |
| `GOV_GAP_CI_LANE_001` | `governor wrap --ci-kind` + `governor ci verify` live, commits `a56e586` + `ef05c09`, 43 tests |
| `SCAR_FINGERPRINT_SPEC` | `failure_kind` / `action_type` fields verified in `src/governor/scars.py`, commit `733c948` |
| `CALIBRATION_LAYER_GAP` | `src/governor/signals/calibration_layer.py` + `calibration_methods.py` exist, commits `bcfa564` + `af5c187`. Spec self-declares "retained as design rationale" — intentional. |

### Closeable with caveat (1)

| Spec | Verification |
|------|--------------|
| `GOV_GAP_FRONT_DOOR_001` | Staging deliverables shipped, commit `e14d276`. Spec explicitly says "Do not publish to PyPI yet… Publication is a separate decision" — PyPI publication is *not* in scope for this spec. Whether `agent-governor` ever goes to PyPI is its own conversation. |

### Status correction needed — only real edit in the whole sweep (1)

`specs/gaps/GOV_GAP_NLAI_GATE_001.md` — Current header claims "Shipped. nlai 0.3.0 on PyPI." But:

- Spec described Phase 1 = extract into `libs/nlai/` (same repo, like `receipt_kernel`). **`libs/nlai/` does not exist.** Only `mcp_governor`, `r2wire`, `receipt_kernel`, `receipt_v1` are present.
- Spec Phase 3 = "governor imports from nlai instead of inline." **Zero `from nlai` / `import nlai` in `src/`.** Governor still uses inline `canonical_json`, `Receipt`, claim extraction.
- Reality: the package shipped externally to `~/git/nlai` + PyPI, skipping the in-repo extraction phase entirely. The architectural seam the gap was meant to force has not been cut.

**Proposed edit** (lines 1–5):

```markdown
# GOV_GAP_NLAI_GATE_001: NLAI Kernel Extraction

**Status**: External ship only — `nlai 0.3.0` on PyPI in `~/git/nlai`. In-repo
extraction (Phase 1 `libs/nlai/`) and governor consumption (Phase 3) did NOT
happen. Governor still uses inline `canonical_json`, `Receipt`, claim
extraction. The kernel-boundary motivation remains live debt; the package
shipped, but the architectural seam it was meant to force has not been cut.
**Category**: Architecture / distribution
**Priority**: Medium — adoption vector satisfied externally; 3.x kernel
boundary still open
```

If "governor consumes nlai" is no longer wanted, the alternative is to mark
this gap closed and accept the inline implementations as terminal. Decide
deliberately rather than letting the status field keep lying.

### Partial — NOT closeable (1)

`MCP_GOVERNOR_GATEWAY` — Phase 0 + Seatbelt v1 shipped (commit `7495bdb`, library in `libs/mcp_governor/`, 78 tests). Phase 1 (multi-upstream + transforms + budgets), Phase 2 (HTTP transport, identity), Phase 3 (signing, conformance) explicitly open with declared roadmap. ChatGPT's "reclassify as implemented integration surface" is wrong on the facts — this is partial work with a live roadmap inside the spec itself. Leave it alone. It is neither closed nor v2 backlog; it has its own internal sequencing.

---

## Net for the "Close stale implemented gaps" commit

Only one file actually changes: `specs/gaps/GOV_GAP_NLAI_GATE_001.md` status header. The other four can be "closed" purely in head-space — their status fields are already honest.

If a heavier closeout pattern is wanted (e.g. moving shipped specs to a `specs/gaps/closed/` subdir), the house-style currently does NOT do that — `GOV_GAP_CHAIN_001` and `GOV_GAP_EGRESS_001` are both `shipped` and stay in `specs/gaps/`. Don't invent the subdir; matches existing convention.

Suggested commit shape if doing the NLAI edit alone:

```
Correct GOV_GAP_NLAI_GATE_001 status: external ship, not in-repo extraction

The header claimed "Shipped. nlai 0.3.0 on PyPI" but Phase 1 (libs/nlai/)
and Phase 3 (governor consumes nlai) never happened. Governor still uses
inline canonical_json, Receipt, claim extraction. Surface the gap honestly
instead of letting the status field cosplay as completion.
```

---

## Re-entry Checklist

1. Read this file
2. Verify nothing major shifted since 2026-05-18 (`git log --since 2026-05-18 --oneline`)
3. ~~Re-verify the four "no edit needed" specs are still accurate~~ — **DONE 2026-05-18** (NLAI status corrected and committed as `0f2e0c4`)
4. ~~Apply the NLAI status correction~~ — **DONE 2026-05-18** (commit `0f2e0c4`)
5. Move to step 2 of ChatGPT's plan (the four new 3.x gap specs in `git status` untracked: `CORRECTIVE_TRANSITION_BOUNDARY`, `GATE_DOCTRINE_SPEC`, `PUBLIC_GATE_CONFORMANCE`, `WITNESS_INVARIANCE_QUALIFICATION`)
6. ~~Then egress wiring~~ — **DONE 2026-05-18** (commit `53a8367`, 7 regression tests, gap spec updated with explicit remaining-work breakdown)
7. **New candidate added 2026-05-18:** `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` — drafted gap spec covering the verified finding that override expiry is administrative metadata, not gate-time enforcement. Forcing case: expired override still satisfies anchors; `check_override()` exists but has zero gate-time callers. Doctrine ratified with operator (three keeper lines from ChatGPT). Implementation NOT started; awaiting promote-to-`specs/gaps/` after first-cut acceptance criteria are ratified.

## New Candidate (Time-Discipline Audit)

Added 2026-05-18. ChatGPT prompted a cross-constellation time-discipline framing; AG-side audit produced one sharp finding worth its own gap spec:

> Override expiry exists as administrative metadata, not as authorization enforcement.

Draft at `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md`. Hard constraints from the framing (DO NOT violate next session):

- Single gap spec, not a doctrine bouquet
- Do NOT launch a global `datetime.now()` cleanup (390 call sites is a smell, not a forcing function)
- Do NOT attempt Wicket-style atemporal kernel for AG in one pass
- First forcing case is **expired override still satisfying a gate** — fix that, get a passing regression, then stop
- Adjacent observations (single-phase GateReceipt timestamp, `evaluation_time` parameterization) stay in the Verified Evidence section as context, NOT as sibling specs

Reframe to keep in view: this is an authority lifetime problem with time as the medium, not a time problem with authority as the surface. The fix is gate-path enforcement of the condition that authorized the standing — not better timekeeping.

Promote `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` to `specs/gaps/` once first-cut acceptance criteria are ratified with operator.

Delete this file after the plan has been executed.
