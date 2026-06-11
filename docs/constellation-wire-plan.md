# Constellation Wire Plan — seams, transports, phases

**Status: orientation / re-entry map. PROVISIONAL, candidate, non-binding.**
Filed 2026-06-12. Routine descriptive artifact — it records how the constellation
wires up *today* and in what order seams promote; it authorizes nothing.

This is the third companion in the orientation set:

- `docs/agent-governor-meta-plan.md` — the **planes** that exist and the
  directional kernel that binds them (the *logical* wiring).
- `docs/constellation-zoning.md` — the **organs that do not exist yet** and the
  one-way doors (the *deferred* wiring).
- **This file** — the **physical wiring**: which transport each seam uses right
  now, which phase promotes it to what, and the probes that tell you which phase
  a seam is in when you re-enter cold.

Why it exists: reconstructing wiring state after a focus shift kept requiring a
re-derivation pass (grep the orchestrator, re-read the launch plan, re-read the
Rust ruling). This file is that derivation, done once, with checkable probes.
**When this file and the code disagree, the code wins — update the file.**

---

## The wiring invariant (load-bearing)

Every cross-repo seam in AG is built as a **SPEC-honoring harness**: the client
owns the seam's types, refusal vocabulary, receipt emission, and pre/post-call
gates; the actual sibling call is an **injected callable** supplied at
construction time.

> **Promotion to live wiring replaces the injected callable at harness
> construction. It never moves the seam boundary, never widens a refusal
> vocabulary, and never relocates receipt emission.**

Corollaries:

- The seam's tests (stub-driven) remain valid after promotion — they pin the
  contract, not the transport.
- A live transport that needs a new refusal kind is a *seam change*, not a
  wiring change — it goes through the closed-vocabulary ceremony, not through
  the adapter.
- Per the meta-plan's artifact table: binding artifacts (standing grant,
  admission, capacity request/consume) get handshake-only, fail-closed
  transport; only observing artifacts may ride lossy pipes with classified loss.
- Per zoning §Transport: state crosses as **claims, never shared residence**.
  No shared Redis key / DB table as an implicit bridge, ever.

### Transport-failure mapping (a pre-W2 obligation, added 2026-06-12)

The wiring invariant says promotion never widens the refusal vocabulary. That
rule can only *hold* if each seam declares, before it goes live, how transport
failure maps onto its existing typed refusals. **The stubs cannot model the one
thing live transports add: failure.** An in-process injected callable cannot time
out, half-deliver, reorder, or drop a connection — so the contract the pinning
tests pin has never been exercised on the failure axis. The first network blip
after promotion would otherwise become an unhandled exception wearing a surprise
hat.

So each W2 promotion carries a **declared transport-failure mapping**: timeout →
which existing refusal, partial/garbled response → which, connection refused →
which (all `cannot_testify`-shaped — a missing attestation fails closed, it does
not fabricate consent). And the cheap way to verify the mapping *before* it is
live: teach the stub to **inject** those failures — a stub that times out and
returns garbage on command, with a pinning test per mapped refusal — then
promote. Chaos-lite while it is still injectable.

Status is tracked per seam in the inventory's **failure-map** column
(`declared` / `tested` / `n.a.`). Today every cross-repo seam is `n.a.` — they are
in-process stubs with no transport to fail. The column flips to `declared` then
`tested` as part of each seam's W2 promotion (the second checkbox in W2's
per-seam discipline).

---

## Seam inventory (state as of 2026-06-12)

The authority chain — the spine everything else hangs off:

```
NQ finding ─→ standing ─→ wicket ─→ LA grant ─→ LA consume ─→ effect
 (testimony)  (entitle)   (admit)    (reserve)    (spend once)
```

Composed end-to-end by `cooked_context_orchestrator.py` (`run()`). The success
edge now passes the fence: it returns `OperationalConsumed` (origin `observed`)
or `DemonstratedConsumed` (every other closed mode) — **not** a bare
`ConsumedResult` — and `confer_operational_effect()` is the spend wall that
accepts only the operational type (Wall 1, shipped 2026-06-12). Receipts link
via `parent_receipt_ids`; every emission is stamped with `origin_mode` by
`_OriginModeReceiptSink`.

`failure-map` column: how transport failure maps to typed refusals (see §pre-W2
obligation). `n.a.` = in-process stub, no transport to fail; flips to
`declared`/`tested` at each seam's W2 promotion.

| Seam | Sibling | Transport today | Status | failure-map | Promotes when |
| ---- | ------- | --------------- | ------ | ----------- | ------------- |
| Standing | `~/git/standing` (Rust) | injected `verify_fn` (`standing_client.py`) | SPEC stub; Rust-conformance fixtures | n.a. | W2 — first live-dogfood consumer |
| Wicket admission | `~/git/wicket` (Rust) | injected `wicket_check_fn` (`wicket_client.py`); composes standing internally | SPEC stub | n.a. | W2 — with standing (same chain) |
| Linear Accountant | `~/git/linearaccountant` (Rust, lib frozen 2026-06-04) | injected request/consume/verifier callables (`linear_accountant_client.py`) | SPEC stub; never-mints; closed refusal kinds verbatim from lib.rs | n.a. | W2 — convertible spend path appears |
| Orchestrator | (composes the three above) | in-process (`cooked_context_orchestrator.py`) | harness; **origin fence WIRED into success edge (type split + spend wall), 2026-06-12** | n.a. | W1 fence wiring DONE; chain promotes with its seams |
| NQ findings | `~/git/nq-root/nq` | file input: `nq.finding_snapshot.v1` JSON via `drill_runner.py --finding-json` | harness; `origin_mode=drill`; byte-identical across the six scenarios | n.a. | W2 — live observed-mode feed |
| Night Shift | `~/git/scheduler` | NS→AG translation (`nightshift_adapter.py`): frozen verdict mapping into `policy_engine` | translation stub; NS calls AG, never back | n.a. | W2 — nightshift live dogfood (the first natural one) |
| Continuity (doctrine) | continuity MCP | lazy import, graceful degradation (`doctrine.py`) | **live-when-present**; read-only, quality-marked | absence → quality-marked (already) | already terminal — stays advisory |
| Z3 verifier | `~/git/verifier` | lazy import, fail-open (`constraint_gate.py`) | **live-when-present**; verdict mapped, errors → observe | error → observe (already) | belongs at the **wicket** seam long-term (meta-plan §Z3), not AG kernel |
| Codex | external CLI | NDJSON post-hoc audit (`codex_hooks.py`) | audit only, no gating | n.a. (observe-only) | per `CODEX_RATCHET_STANDING_GAP`: reviewer → chat-reporting → executor, each earns standing separately |
| Preflight membrane | daemon consumers | injected `PreflightClient` protocol (`governed_dispatch.py`) | protocol definition; blocked ⇒ transport_call never invoked | declared (blocked ⇒ no call) | with whatever consumer adopts it |

**Already-live wiring** (for contrast — these are real transports today, not
stubs): the **daemon** (JSON-RPC over stdio/Unix socket; Guvnah via stdio, Maude
via socket) and the **runtime supervisor adapters** (Claude Code via Unix-socket
hooks, Gemini CLI via hook scripts — fail-closed pre-tool gate, drill-verified).
The execution plane is wired; it is the *authority chain* that still runs on
injected stubs.

---

## Phases

Named W0–W4 to avoid colliding with the instrumentation spine's Phase A–D and
the demo's D0 (W1 *contains* D0).

### W0 — Harness state (DONE; this is "now")

Everything in the table above as-is. What W0 already guarantees:

- Seam types, closed refusal vocabularies, receipt linkage, and pre/post-call
  gates exist and are pinned by tests (stub-driven).
- Origin-mode custody bridge active: NQ's closed set `{observed, drill, replay,
  synthetic}` (migration 057) mirrored verbatim + AG-internal `{cli_origin,
  stub_origin}`; stamped into every `evidence_bundle` (custody-bound via
  `evidence_hash`).
- `operational_admission()` predicate shipped (`ab6d196`): allowlist
  `{observed}`, typed refusals, pinning test (novel string never admitted).
- Deterministic drill path: six-scenario gauntlet + D3 confabulation, four
  receipts per run, show-surface poster.

### W1 — D0 launch runway (IN PROGRESS; current focus)

The slab the demo sits on (`working/launch-plan-2026-06-11.md` owns the
sequence; this is just its wiring view). Order:

1. **Fence wiring — DONE 2026-06-12.** `operational_admission(origin_mode)` gates
   the orchestrator's success edge as a **type split** (ratified option-B-amended,
   not a veto): the chain still mechanically completes (drills demonstrate
   structure, per zoning §Evidence classes), but a non-`observed` origin yields a
   `DemonstratedConsumed` — a *distinct type* the spend wall
   (`confer_operational_effect`) refuses by `isinstance`, not a boolean a consumer
   must remember to check. `OperationalConsumed` (origin `observed`) is the only
   type that confers effect. Negative pinning tests are the wall's teeth
   (`tests/test_operational_spend_fence.py`). The launch plan's "synthetic/drill/
   replay refuses to reach operational consequence" holds — it refuses by *type
   unreachability*, not a flag. **Wall 2** (LA per-class unit matching →
   `unit_origin_mismatch`) is the arithmetic complement: *named, not built* —
   it is a cross-repo LA contract change (`working/candidate-la-unit-class-fence.md`).
2. **Golden corpus — DONE 2026-06-12 (with one flagged gap).** The decision
   chain's `input → verdict` pairs are frozen in `golden/corpus/*.json` and
   enforced by `tests/test_corpus_contract.py` (24 tests): the live chain must
   reproduce each frozen verdict, drift breaks the test, updating a golden is a
   deliberate act. Per `memory/rust_kernel_port_ruling` this — not the Python —
   is the kernel contract (socket-cut prep). Seven cases: valid-passes, four
   custody refusals, gap-accounted, and **synthetic-evidence-fenced** (the
   just-shipped Wall 1, pinned corpus-wide: every simulated-origin case is
   `operational=false`, even the ones that consume). The corpus labels the
   near-neighbor honestly (`03-standing-unverifiable-refused` ≠ temporal lapse)
   rather than mislabel; the hero specimen it flagged shipped as item 2.5.
2.5. **Temporal-lapse hero specimen — DONE 2026-06-12.** The two-clock temporal
   lapse the launch plan designates the demo's best specimen — flagged as a gap
   at corpus-freeze, now built as the `temporal-lapse` PAIR (`08`/`09`). Real
   machinery: `StandingSpendabilityGate` (`src/governor/standing_spendability.py`)
   at the standing→spendability edge refuses a spend whose standing lapsed past
   its horizon by exercise time, with the ratified kind
   `standing_before_spendability_not_bounded` and a receipt carrying the gap
   (`gap_ns`/`bound_ns`/`overage_ns`) over a **mandatory** attested monotonic
   `gap_basis` (`process_monotonic` / `boot:demo-single-host` for the single-host
   demo — a gap is a difference between compatible clock witnesses, not numbers;
   wall time rides along display-only and is never the gap basis; multi-host later
   is a value change, not a schema change). Ships as a *pair*: the impostor refuses, the
   legitimate twin (exercise within horizon) passes the same gauntlet — both
   halves of the demo's Act-1 contrast frozen. Refusal fires before any capacity
   is spent (lapse costs no budget). New refusal kind is an AG-internal S4-lite
   addition (not cross-repo). The check is its own seam, NOT folded into the
   standing client (witness exposes the clocks; policy decides the gap — zoning
   §Standing). Tests: `tests/test_standing_spendability.py`,
   `tests/test_drill_temporal_lapse.py`, `tests/test_clock_witness.py` (the
   incompatible-basis refusals), corpus block-pin incl. the missing-`gap_basis`
   negative.
3. **Refused-spend script + show surface — DONE 2026-06-12.** The demo's Act-1
   *depth* surface (one incident, the temporal contrast) — distinct from the
   codex-frozen `drill_poster` *breadth* surface (the seven-invocation gauntlet),
   left untouched. `src/governor/demo_refused_spend.py` runs the temporal pair
   (legitimate twin spends cleanly / impostor refused on the gap), renders a
   deterministic receipt-forward contrast showing the gap over its named monotonic
   `gap_basis`, and asserts the **integrity tripwire**: the impostor refused for
   the RIGHT reason (temporal lapse at `standing_spendability_seam`, spending no
   capacity), same gauntlet as the twin, neither run operational. Stranger-facing
   one-command entry `demo/refused-spend.sh` (the `./demo/refused-spend.sh` the
   zoning forcing-case named; exits nonzero if the tripwire fails — a demo that
   passes for the wrong reason fails loudly). Framing copy is provisional /
   operator-ratifiable (NOT micro-frozen like the poster). Tests:
   `tests/test_demo_refused_spend.py` (8).
4. **Proof seam — DONE 2026-06-12.** Act 3 (necessity): the refusal class →
   the Lean class-boundary theorem that licenses it. `src/governor/proof_seam.py`
   maps each refusal kind to a verified PUBLIC-SHIPPED [1.0] theorem — the hero
   (`standing_before_spendability_not_bounded`) → `Freshness.expired_not_fresh`
   (`¬(now ≤ expires+skew) → ¬Fresh`, the t=51 > horizon=50 lapse exactly);
   observation≠standing → `Authority.no_standing_never_authorized`;
   standing≠admissibility → `Authority.no_basis_never_authorized`. Each verified
   2026-06-12 (exact name, complete proof / no `sorry`, custody class). Honest
   framing baked in: the theorem proves the *class*, the receipt proves the
   *instance*, the citation is the link — NOT "Lean proved production safe."
   Classes the kernel does NOT prove (linearity/`already_consumed`, the operational
   fence) are marked `NO_KERNEL_THEOREM` with a reason, never given a borrowed
   citation. The link is DERIVED from the receipt's `refusal_kind` (the theorem is
   about the class), not stored per-receipt. Wired into the demo surface as the
   Act-3 descent. `~/git/rkl` is [scratch] lab, explicitly NOT a citation source.
   Tests: `tests/test_proof_seam.py` (8, the tier discipline).
5. **OPA contrast shim** — ~100 lines, demo-grade only, Act 2.5. Concretizes the
   deferred verdict seam with an off-the-shelf part; NOT a product surface.

**Exit criteria:** a stranger reproduces one end-to-end refusal in <15 min;
integrity tripwire holds (it cannot pass/refuse for the wrong reason — the BA3
`LA_ONLY` bypass class); Show HN gate items all true. **Nothing in W2+ starts
before this exits** — launch is the forcing function and the brake.

### W2 — Live seam promotion (POST-LAUNCH; one seam at a time)

Replace injected callables with real cross-repo clients, under the wiring
invariant. Each seam promotes on its own forcing case — **no batch "wire up the
constellation" event** — and clears **two checkboxes** before going live:

1. **Forcing case** named (the seam's "Promotes when" cell).
2. **Transport-failure mapping** declared *and* tested (the §pre-W2 obligation):
   the stub is taught to time out / half-deliver / drop, with a pinning test per
   mapped refusal, before the real transport replaces it. `failure-map: tested`.

- **Night Shift live** — the first natural dogfood (`memory/scheduler_repo`).
  NS calls AG's adapter for real `check_policy` / `record_receipt` /
  `authorize_transition`. Likely first because the adapter is translation-only
  and the daemon transport already exists.
- **Standing + Wicket live** — Rust binaries behind the existing callables.
  Promote together (wicket composes standing). Z3 integration lands at this
  seam when it lands, per meta-plan.
- **Linear Accountant live** — trigger is unchanged from
  `memory/linearaccountant_repo`: *a convertible spend path appears*, not
  co-location convenience.
- **NQ observed-mode feed** — live FindingSnapshots with `origin_mode=observed`
  arriving by transport rather than `--finding-json`. This is the first moment
  the W1 fence admits anything; until then every chain input is fenced
  non-operational by construction.
- **Transport choice** is a W2 decision *per seam*, deferred until promotion:
  subprocess, socket, or WLP-carried claims. Constraint, not choice: binding
  artifacts fail closed; the pipe may be dumb (WLP owns custody semantics, per
  zoning §Transport).

### W3 — Rust decision kernel (POST-LAUNCH; gated by the standing ruling)

Per `memory/rust_kernel_port_ruling`, verbatim discipline: narrow **decision
kernel only** — not control plane, not scaffold. The W1 golden corpus is the
frozen contract the crab fills. **No silent Python fallback**: dual-engine
divergence gets a receipt, not a shrug.

### W4 — Deferred organs (NO DATES; forcing-case gated)

Owned by `docs/constellation-zoning.md` — not duplicated here. The wire-plan
view is one sentence: **none of W0–W3 may foreclose them** (the one-way-door
table is the checklist). Watch-list from zoning: retraction transport and the
verdict seam are refusal-already-inexpressible; Notary graduated to its own
project; temporal authority is the second gravity center with no plane.

---

## Re-entry probes (cold-start state reconstruction)

Run these instead of re-deriving. Each answers "which phase is this seam in?"

```bash
# Is the fence wired into the success edge yet? (W1 item 1 — DONE 2026-06-12)
grep -n "operational_admission\|confer_operational_effect" src/governor/cooked_context_orchestrator.py
#   → WIRED: run() calls operational_admission() on the success edge and
#     returns OperationalConsumed (observed) vs DemonstratedConsumed (else);
#     confer_operational_effect() is the spend wall that accepts only the
#     operational type. Negative pinning: tests/test_operational_spend_fence.py.

# Does the golden corpus exist yet? (W1 item 2)
ls golden/ demo/ 2>/dev/null; git log --oneline -5 -- golden/ demo/

# Are the chain clients still stubs? (W0 vs W2)
grep -rn "Promotion: replace with real cross-repo client" src/governor/
#   → hits = still W0 stubs. A seam missing from the hits has been promoted.

# What does the chain refuse with today? (vocabulary drift check)
grep -n "CLOSED_REFUSAL_KINDS" src/governor/linear_accountant_client.py

# Fence vocabulary still closed-world?
python3 -m pytest tests/test_origin_admission_fence.py -q

# Launch sequence position
head -40 working/launch-plan-2026-06-11.md   # §Sequencing is the to-do list
```

Standing orientation docs, in reading order when fully cold:
`agent-governor-meta-plan.md` (planes) → this file (wires + phases) →
`constellation-zoning.md` (what's deferred) → `working/launch-plan-2026-06-11.md`
(the current to-do list).

---

## What this file is not

- Not a roadmap with dates. Phases order work; forcing cases schedule it.
- Not authorization to promote any seam. W2+ items each gate on their named
  forcing case.
- Not the owner of any seam contract. Siblings own their sides (zoning
  §Disposition 4); this file records AG's view of the wiring only.
- Not a substitute for the launch plan — W1 defers to it entirely.
