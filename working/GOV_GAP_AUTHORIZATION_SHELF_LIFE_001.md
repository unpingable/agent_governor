# GOV_GAP_AUTHORIZATION_SHELF_LIFE_001

## Title
Override expiry is administrative metadata, not authorization enforcement: expired authorizations still bind at gate time.

## Status
**Candidate — parked in `working/`, refined 2026-05-19.** Drafted 2026-05-18 from a verified forcing case (override expiry checked administratively, not at gate time). Refined 2026-05-19 with two convergent inputs that arrived after the original draft:

- **Formal warrant landed:** `~/git/lean/LeanProofs/Admissibility/Freshness.lean` (added 2026-05-19, not yet committed at refinement time) formalizes the doctrine as a metric-time admissibility kernel with four typed failure modes and one positive composite predicate (`Fresh`). The Lean module names its canonical consumer as `~/git/standing`; AG is a sympathetic consumer of the same warrant.

- **Reference implementation already half-wired in AG:** `src/governor/standing/workload_identity.py` (slice 2A/2B/2C, ~40 days ago) carries an `AssessmentResult` enum (line 40) with the exact four temporal verdicts the Lean kernel proves: `EXPIRED`, `NOT_YET_VALID`, `ASSESSMENT_COMPROMISED`, plus `VALID`. AG already verifies Standing-issued WorkloadId tokens on chat RPC paths. **Identity-side integration is done; authorization-grant-side integration is not.** This gap is the second half.

The combination means the gap is now closer to ratification-ready than initial-draft. Awaiting operator decision on (a) promote to `specs/gaps/` and (b) start implementation, or continue parked.

## Origin

Filed 2026-05-18 during an end-of-session time-discipline audit prompted by ChatGPT's cross-constellation framing (NQ/NS / Wicket / WLP / RPP / Continuity / AG). ChatGPT's AG-specific reading:

> AG is time-sensitive because authorization decays. Not every authorization should remain admissible forever just because it was once granted.

The audit asked: does AG actually enforce that? An Explore-agent sweep across `gate_receipt.py`, `ttl.py`, `overrides.py`, `governed_activity.py`, `signals/decision_evidence_lag.py`, `standing/`, and Receipt v1 schema produced one verified finding sharp enough to warrant a gap spec on its own. The other observations cluster around it as second-order effects, not separate gaps.

ChatGPT's framing reframe (kept as load-bearing):

> This is not really a time problem first. It is an authority lifetime problem. Time is the medium. The actual bug is: standing granted under condition C; condition expires; standing still binds.

## Problem Statement

`src/governor/overrides.py` defines `OverrideRecord` with an `expires_at` field (line 52), an `is_expired` property (line 65), a `check()` method on `OverrideManager` that consults expiry (line 90), and a public convenience function `check_override(gov_dir, anchor_id, path)` at line 453. The function exists. The expiry logic exists. The administrative surface (CLI `governor override list`, MCP endpoints, status rollup) correctly filters by expiry.

**`grep -rn "check_override(" --include="*.py" src/` returns exactly one result: the definition itself.** Zero callers anywhere in the gate-evaluation paths. Continuity checks, anchor checks, evidence-gate checks, and the security verifier do not consult override expiry at decision time. They consult the `OverrideManager` administratively (CLI display, MCP listing) but never to decide whether an action is currently authorized.

Concrete laundering path:

```
T0 = 10:00 — `governor override create --anchor A --scope "src/**" --expires 1h --because "incident X"`
T1 = 11:00 — override.expires_at passes
T2 = 14:00 — agent edit lands; gate consults anchor A; finds no live "anchor satisfied" verdict;
             no caller asks `check_override("A", "src/foo.py")`;
             the expired override sits in the file system but does not surface a "blocked: expired authorization" verdict.
T3 = receipt emitted recording "anchor A blocking" — but the receipt does not record that an expired override was present and ignored. The expired authorization is invisible to the audit trail.
```

The dual of this — and the more dangerous form — is when a downstream consumer believes the override is still active because the administrative surface shows it (with an "expired" flag they may not inspect carefully), and assumes the gate handled it. That assumption is wrong. The gate does not look.

## Doctrine

Three keeper lines (lifted from the ChatGPT framing, ratification target):

> **Authorization has a shelf life unless the policy says otherwise.**

> **No timestamp may impersonate another timestamp.**

> **Expiry metadata is not enforcement unless the gate path checks it.**

The first is the substrate claim. The second is the cross-cutting invariant (operates beyond this gap, but this gap is its first AG-side firing case). The third is the procedural rule that makes the first two stick.

**Formal warrant (added 2026-05-19):** `~/git/lean/LeanProofs/Admissibility/Freshness.lean` proves the doctrine structurally for metric-time admissibility. The Lean module's positive composite (`Fresh now issued expires skew maxDiv`) and four negative theorems (`expired_not_fresh`, `not_yet_valid_not_fresh`, `incoherent_not_fresh` / `not_precedes_not_fresh`, `divergence_excessive_not_fresh`) give AG a typed vocabulary it can cite rather than assert. The module's own keeper-block reads:

> Expired evidence cannot prove current standing. Future-issued evidence cannot prove current standing. Incoherent intervals cannot prove standing. Excessive clock divergence makes the assessment unsafe.

The Lean keepers and the AG doctrine are different surfaces of the same claim; the Lean side is finer-grained because it splits the third failure mode (incoherent interval) into two structurally distinct theorems under opaque `Time.le`. AG should mirror that finer split when implementing.

## Cross-Boundary Doctrine (added 2026-05-21)

Two further keepers were grounded for this gap on 2026-05-21 during the disposition of a failed-grounding cross-fence drop (`working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md`). The original drop's primary thesis did not ground in AG (no `outOfScope` verdict in tree), but two cross-cutting observations did — they have direct forcing cases in the shelf-life surface and are imported here as adjacent doctrine.

> **Receipt is what you can copy; authority is what you spend.**

For shelf-life: the override file in `.governor/overrides/` is a *receipt of a past authorization decision*, not live authority. Its `expires_at` field records what the authority *was* valid for; at gate time, the authority itself must be re-derived from current state, not assumed live from the receipt-shaped artifact. Copying the file, reading it administratively, or surfacing it in `governor override list` operates on the receipt; only the gate path operates on (or refuses) the authority.

> **Constructive bundling eliminates TOCTOU only within the construction boundary. Across daemon/CLI/serialization boundaries, authority must be revalidated, sealed, or treated as a receipt claim rather than spendable authority.**

For shelf-life: the override creation path runs in one process (daemon or `governor override create` CLI invocation). The override consumption path runs in a different process (continuity checker, anchor gate, evidence gate — any of which may run from a separate `governor` invocation reading the on-disk JSON). The construction-time invariant (`expires_at` is in the future, `is_expired` returns False) is a true claim *at that instant in the constructing process*. By the time a separate consuming process reads the file, that claim must be re-verified against the consumer's current clock. The current AG implementation has the re-verification primitive (`OverrideManager.check()` / `is_expired`) but does not invoke it on the gate path — so the construction-time invariant is being trusted across the process boundary without revalidation. **That is the laundering shape this gap closes.**

These two keepers compose with the three from the Doctrine section as follows. The Doctrine section says authorization has a shelf life, no timestamp impersonates another, and expiry metadata is not enforcement without a checking gate. The Cross-Boundary section adds: even when expiry metadata IS being checked (somewhere), checking it once at construction is insufficient if the artifact subsequently crosses a process boundary; the consumer must re-check, and the gate path is the consumer.

Provenance: keepers lifted from a papers-side Claude filing dropped into `specs/gaps/` on 2026-05-21. The original filing's primary thesis (runtime laundering of an `outOfScope` verdict) failed AG's grep-first grounding audit and was moved to `working/`. The lifted keepers retained because they have AG-side forcing cases the original filing did not name.

## Verified Evidence

1. **`overrides.py` has the machinery.** `expires_at` field (line 52), `is_expired` property (line 65), `OverrideManager.check()` consults expiry (line 90), public `check_override()` convenience at line 453.

2. **`check_override()` has zero gate-time callers.** `grep -rn "check_override(" --include="*.py" src/` returns the definition only.

3. **Administrative surfaces filter by expiry; evaluation paths do not.** `OverrideManager.list_active()` filters at line 298. CLI `governor override list`, MCP override endpoints, and `status_rollup.py` consult the manager for display. The continuity checker, anchor checks, evidence gate, and security verifier do not consult it during decisions.

4. **`GateReceipt` carries a single-phase `timestamp` field** (`gate_receipt.py:343`). Decision time, authorization time, receipt emission time, and the time of the action the receipt records are all collapsed into one wall-clock value. The receipt cannot answer "when was this authorized vs when did the action run" — they are by construction the same number.

5. **Roughly 390 `datetime.now()` call sites across the codebase.** Suggests gates bake current time in rather than accepting an `evaluation_time` parameter (Wicket-style discipline). This is a smell that frames downstream remediation, **but is explicitly NOT the first fix.**

6. **Standing-side `AssessmentResult` enum is already in AG-tree, ready to import.** `src/governor/standing/workload_identity.py:40` exposes seven verdicts: `VALID`, `INVALID_SIGNATURE`, `EXPIRED`, `AUDIENCE_MISMATCH`, `NOT_YET_VALID`, `REPLAY_DETECTED`, `ASSESSMENT_COMPROMISED`. Four of these map directly onto Lean's `Freshness` theorems (the temporal subset: `EXPIRED`, `NOT_YET_VALID`, `ASSESSMENT_COMPROMISED` for incoherence, `ASSESSMENT_COMPROMISED` for clock divergence). The verdict-name open question from the initial draft (q1: "what's the verdict name?") is **answered**: reuse Standing's enum names; do not invent.

7. **Clock-divergence as a freshness axis was not named in the initial draft.** Lean's `DivergenceAcceptable` predicate (`Time.absSub verifier issuer ≤ maxDiv`) names a real seam: when verifier and issuer clocks have drifted too far, the assessment itself is unsafe — distinct from "evidence is expired." Relevant for AG whenever an authorization is issued by one process/host and consumed by another (overrides created by a daemon RPC and consumed by a CLI later; cross-session overrides; future federated cases). Standing's `ASSESSMENT_COMPROMISED` is the verdict; AG has no current implementation, but the gap spec must name the axis so it doesn't get re-discovered.

8. **AG-side Standing identity integration is already shipped; authorization-grant integration is not.** Slice 2A/2B/2C wired Standing's WorkloadId verification into chat RPC paths (`require_standing` config, `verify_workload_id_token`, fail-closed semantics). Identity-side: done. The override-evaluation path does NOT call any Standing-style grant assessment; it consults a Python-local JSON store with `is_expired` checked only administratively. This gap closes by extending the existing Standing wiring pattern from identity to grants.

## Non-Goals

These are bright-line exclusions from this gap. Each one is a real surface that could be addressed; none belongs in the first cut.

- **Not a global `datetime.now()` cleanup.** 390 call sites is a smell, not a forcing function. Do not refactor.
- **Not Wicket-style atemporal kernel for AG in one pass.** The boundary discipline (`validate(input, context, evaluation_time)` instead of hidden `now()`) is correct doctrine but a multi-quarter refactor. Out of scope here.
- **Not a multi-spec ontology sprawl.** No companion `GOV_GAP_EVALUATION_TIME_PARAM_001`, `GOV_GAP_RECEIPT_PHASE_TIMESTAMPS_001`, etc. **One spec. One forcing case.** Adjacent observations stay in the Verified Evidence section as context for *why* this is load-bearing, not as siblings.
- **Not policy-version-freshness enforcement.** `OPERATIONAL_SLA.md` raises that as separate v3 work. Different mechanism, different gap.
- **Not warrant/grant lifetime beyond overrides.** Other authority-bearing artifacts (warrants, scope grants, intent forms) may have similar gaps. Confirm one fix in the first artifact (overrides) before generalizing.

## Acceptance Criteria

Closure of this gap means **the first forcing case fails** for the right reason, with a receipt that records the gap:

1. **An expired override must not satisfy a gate.** When the gate evaluates an anchor that an expired override previously covered, the gate must not treat the override as binding. The verdict must reflect the anchor's underlying state, not the expired override.

2. **The resulting receipt distinguishes three timestamps:**
   - `override.expires_at` (when authorization lapsed)
   - `evaluation_time` (when this gate ran)
   - The matched-rule / verdict reflecting that an expired authorization was found and rejected

3. **The verdict comes from the existing `AssessmentResult` enum, not a new one.** Reuse `AssessmentResult.EXPIRED` for the override-past-expiry case. `NOT_YET_VALID` for the future-dated case (defensive — overrides currently lack `not_before` but the verdict slot is there for when they do). `ASSESSMENT_COMPROMISED` for temporally incoherent overrides (e.g. `expires_at` parses as before creation timestamp). Silent fall-through to a generic "anchor blocking" is insufficient — the specific failure-mode verdict must surface.

4. **Regression test:** construct an override with `expires_at` in the past, then run an evaluation that would have been satisfied if the override were live. Assert (a) verdict is `AssessmentResult.EXPIRED`, (b) receipt records the expiry timestamp and the evaluation timestamp distinctly, (c) the matched-rule names the expired-authorization case, (d) the receipt's evidence bundle includes the override's `jti` (or equivalent unique identity) so audit can trace which expired authorization was rejected.

5. **No silent enforcement-by-omission for unexpired overrides.** This change must not regress the existing "active override satisfies anchor" path. Tests must cover both the expired and the unexpired sides of the same code path, so the new check cannot drift into "all overrides blocked."

6. **Clock-divergence verdict path is wired even if not initially populated.** The `ASSESSMENT_COMPROMISED` verdict slot must be reachable in the gate path's verdict-emission code, even if AG cannot yet detect clock divergence (no cross-host issuer in the current override model). The wiring shape — "this verdict can be emitted" — matters so the next consumer who issues overrides cross-process doesn't have to rebuild the surface. This is *plumbing-without-firing*, not implementation work.

What is **explicitly NOT** in acceptance criteria for this gap:

- Generalization to other authority-bearing artifacts (warrants, grants).
- `evaluation_time` parameterization of gate signatures.
- Splitting `GateReceipt.timestamp` into phase-specific timestamps.
- Cross-gate audit-query API for "receipts whose authorizations have since expired."

Those are real, named in the Verified Evidence section, and stay open after this gap closes.

## Reframe (Load-Bearing)

The first-cut framing is "AG doesn't enforce override expiry at gate time," which is true but undersells the substrate. The deeper claim, from ChatGPT, is that **authorization decay is an authority lifetime problem with time as the medium, not a time problem with authority as the surface**. The substrate failure isn't "we used the wrong timestamp." It's "we granted standing under a condition, the condition lapsed, and the system kept honoring the standing."

This matters for the gap's scope: the fix is not better timekeeping; it is **gate-path enforcement of the condition that authorized the standing in the first place**. The override's `expires_at` is one such condition. Other conditions (policy version, source state, scope axis, operator identity) may eventually need analogous enforcement — but each is its own forcing case, not a generalization of this one.

The "we discovered Kerberos in the basement again" line from ChatGPT is honest about prior art: this failure class is well-known in distributed-auth literature (ticket TTL vs. usage moment, capability revocation latency, lease expiry vs. lease renewal). AG is not inventing a new problem; it is meeting an old one for the first time.

## Relationship to Other Gaps and Sibling Repos

**Sibling-repo convergence (added 2026-05-19) — load-bearing:**

- **`~/git/lean/LeanProofs/Admissibility/Freshness.lean`** — Formal warrant for the doctrine. The Lean kernel proves the four temporal admissibility failure modes structurally; AG cites rather than asserts. Custody: canonical via commit hash + lake build proof gate + ratification rule on changes to `Time` / `TemporallyCoherent` / `DivergenceAcceptable` / `WithinValidity` / `Fresh`. A matching definition elsewhere does not inherit the canonical anchoring. AG's gate-path implementation should mirror the four-theorem structure (one verdict slot per failure mode) and may include a comment-level back-reference to the Lean theorem name (`expired_not_fresh`, etc.) without making the citation load-bearing.

- **`~/git/standing`** — Reference implementation in Rust. Per the slice-1 closeout (~2500 LOC, 85 tests passing, 13 scar mitigations real including time-in-protocol exp/iat/skew, leases + sweep, audience restriction, replay via jti + SQLite seen_jti, TOCTOU CAS, identity-vs-authorization separation, content-addressed receipts at every transition, assessment-compromised firing on temporal/storage incoherence). Standing's closeout runway names AG as "step 1: first real consumer." AG-side identity integration is already done (slice 2A/2B/2C); this gap is the grant-side completion. The implementation pattern from `src/governor/standing/workload_identity.py` (verify token, AssessmentResult, fail-closed, principal_ref into receipt) is the template the override path should follow.

**AG-side adjacent gap specs:**

- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Adjacent. Names "stale prose / ambiguous authority as binding" as a laundering path. Form discipline (C3) shipped; content semantics (is basis still admissible at decision time?) does not. This gap is the override-specific firing case of that general doctrine.
- **`OPERATIONAL_SLA.md`** — Adjacent. Raises policy-version freshness at decision time. Different artifact (policy bundles), same shape (data that has been validated once is not necessarily admissible now). Cross-pollinate doctrine, do not merge specs.
- **`GOV_GAP_CORRECTIVE_TRANSITION_BOUNDARY_001`** (just-added candidate) — Adjacent. Authority-increasing transitions need typed enforcement. Authorization-decay is the time-axis dual of authority-increase. Likely share doctrine but not implementation.
- **`GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001`** — Adjacent. If the mint is moved (Rust / Lean / Ada), expiry semantics should be in the mint, not in Python policy code. Standing's Rust mint is one such location; the substrate-custody question is whether AG's override creation should ALSO move to Standing (overrides issued by Standing, verified by AG) or stay AG-local with Standing-style verdict surface only. Decide at promote-time.
- **`cadence` repo** — Once this gap closes, doctrine likely promotes upward (per `~/.claude/CLAUDE.md` § "Doctrine promotion") into cadence as a recognized pattern for cross-constellation temporal admissibility.

## Open Questions

1. ~~**What is the verdict name?**~~ **Answered 2026-05-19.** Reuse the existing `AssessmentResult` enum at `src/governor/standing/workload_identity.py:40`. Four temporal verdicts already named, aligned with Lean's four `Freshness` theorems and Standing-side Rust verdicts. Do not invent a new vocabulary.
2. **Where does the check live?** Inside `OverrideManager.check()` (already correct, already consults `is_expired`), or in a new gate-side helper that wraps it? The latter avoids touching the manager but creates a parallel call site to maintain. Refinement note 2026-05-19: this is partly answered by the Standing pattern — verification logic lives in a dedicated module (`standing/workload_identity.py`), consumers call a single entry point, fail-closed semantics are in the verification module not the consumer. A new `governor.authorization` (or `overrides.assess`) module that returns `AssessmentResult` keeps the same shape.
3. **Should AG re-issue overrides as Standing grants, or keep them AG-local with Standing-style verdict surface only?** Two reasonable answers: (a) overrides stay JSON files, AG calls a local `assess_override()` that returns `AssessmentResult`; (b) overrides become real Standing grants, AG calls Standing to issue and verify. (a) is the cheaper first cut and what acceptance criteria currently assume. (b) is the longer-term substrate-custody alignment per `GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001`. Ratify which version closes this gap; if (a), file a follow-up gap for (b).
4. **What about overrides that were used while live and have since expired?** Past receipts referencing them are historically valid (authorization was live at decision time). Do we need a "this receipt's authorization has since expired" audit-query? Not for closure of this gap, but possibly load-bearing for the next one.
5. **Do scope grants (`scope.py`) have the same laundering pattern?** Likely yes (`Grant.is_expired()` exists; verify call-site discipline). Confirm separately; do not bundle.
6. **`not_before` field for overrides?** Currently overrides have `expires_at` but no explicit `not_before` — they're implicitly valid from creation. The `AssessmentResult.NOT_YET_VALID` verdict is wired through but unused on the AG side. Decide whether overrides gain a `not_before` field for scheduled-future activation, or whether that verdict slot stays formally available but practically inert. Aligns with Standing's grant-activation lifecycle (`activate` is a distinct step from `request`).

## Provenance

- 2026-05-18 — Time-discipline audit, ChatGPT prompt, Explore-agent sweep
- 2026-05-18 — Override-expiry enforcement claim verified via `grep -rn "check_override(" --include="*.py" src/`
- 2026-05-18 — ChatGPT's three-line doctrine ratified by operator as keepers
- 2026-05-18 — Drafted into `working/` as parked candidate
- 2026-05-19 — `~/git/lean/LeanProofs/Admissibility/Freshness.lean` added (untracked at refinement time); cited as formal warrant
- 2026-05-19 — Standing-side state forwarded by operator (slice-1 closeout: 85 tests, 13 scar mitigations, AG named as step-1 consumer in closeout runway)
- 2026-05-19 — AG-side `src/governor/standing/workload_identity.py:40` `AssessmentResult` enum confirmed in-tree; verdict-name open question resolved
- 2026-05-21 — Papers-side Claude dropped `GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001` into `specs/gaps/` via a cross-fence move. AG-Claude two-grep audit (`grep -rinE "out_?of_?scope|outOfScope" src/governor/`) failed to ground primary thesis: no `outOfScope` verdict surface in AG today. Three matches in tree (autopilot OutOfScopeAction enum, writing_ticketing reason string, constraint_compiler comment) are not classification-to-authority surfaces.
- 2026-05-21 — Failed-grounding spec moved to `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md` per AG grep-first discipline; `specs/gaps/` not used as quarantine zone for imported doctrine.
- 2026-05-21 — Two grounded keepers lifted from the cross-fence drop into this spec's new Cross-Boundary Doctrine section. The keepers have AG-side forcing cases (override receipts crossing the daemon→CLI process boundary) that the original filing did not name. The firewall held: AG-Claude refused to import the speculative outOfScope framing as fact but kept the parts that ground in AG soil.
- Pending — Operator decision on promote-to-`specs/gaps/` and on (a)-vs-(b) implementation cut in Open Question #3
