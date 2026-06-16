# Campaign card — Operational-authority census (read-only)

**Opened:** 2026-06-16
**Provenance:** operator directive after the `BudgetPolicy` own-goal
(`working/audit-2026-06-16-budgetpolicy-custody.md`) — stop one-off actuator
guesses; do a doctrine-first census instead.

## Question

> Which operational powers does AG currently exercise, who is supposed to own
> them eventually, and which ones lack an existing ruling?

## Invariant (load-bearing)

**Doctrine-first.** For every candidate surface, grep `specs/gaps/`, `working/`,
`docs/`, and memory pointers for an existing gap/debt/decision **before**
classifying. A surface is only "unruled" after that search comes up empty. The
failure mode this campaign exists to prevent is re-discovering an
already-adjudicated debt as if it were new.

## Allowed

- Read code + docs; grep for rulings; produce a census **table** + a verdict.
- Name genuinely-unruled seams as **candidates** (reserved names, non-binding).

## Forbidden

- Building anything; opening new build campaigns.
- Modifying the BA3 forbidden-work fence (`post-mvp-debt-ba3-hardshort-to-la.md`).
- "Rescuing" a parked surface by wiring a consumer (dependency reversal — the P4
  lesson).
- Reclassifying any BA3 surface downward without LA backing.
- Producing a "new architecture." The deliverable is a table, not a design.

## Classification vocabulary

`active-and-owned` · `transitional` · `externally-destined` (LA/other repo) ·
`parked` (ruled, deliberately not built) · `dead` (configured but inert) ·
`unruled` (live authority, no governing doc).

## Per-surface record fields

actual consumer (file:line) · live & behavior-changing? · config source ·
custody strength (receipted/hash-bound/operator-settable?) · intended terminal
owner · governing doc (or "none found") · classification.

## Exit states

- (a) All live authority is ruled/parked/delegated → declare a **legitimate
  stopping point** until LA (or another dependent) lands.
- (b) N genuinely-unruled seams → list as candidates only.
- (c) Census coverage incomplete → name the unswept surfaces, no silent cap.

---

## RESULTS — 2026-06-16 (five-agent read-only sweep)

Method: 5 parallel agents, one per cluster, each grepping `specs/gaps/` + `working/`
+ `docs/` for a governing doc **before** classifying. Every "live" claim cites a
consumer file:line. Full agent reports retained in the session transcript.

### Master census (one row per behavior-changing surface)

| Surface | Live & behavior-changing? | Custody | Terminal owner | Governing doc | Class |
|---|---|---|---|---|---|
| **Git pre-commit hook** (`hooks.py`/`cli.py:1665`) | YES — blocks `git commit` | **gate_receipt** (`pre_commit`, hash-bound) | AG (core) | ADR 0002 "gate not memory" | **active-and-owned** |
| **Runtime supervisor pre-tool gate** (`supervisor.py:555`) | YES — sends `deny` to backend | canonical EventBus events (not gate_receipt) | AG (core) | `working/tock-01-fail-closed-gate.md` | **active-and-owned** |
| **Egress gate** (`egress_gate.py` via `chat_bridge.py:90`) | YES — raises `EgressBlocked`, stops HTTP | **gate_receipt** (`egress_policy`, redacted) | AG (core) | `GOV_GAP_EGRESS_001` + `..._LLM_PROVIDER_EGRESS_001` | **active-and-owned** |
| **intent_compiler** (`daemon.py:1259`) | YES — live RPC | **content-addressed** (`intent_compiler` receipt) | AG (core) | (none — but well-custodied) | **active-and-owned** |
| **Origin fence** (`cooked_context_orchestrator.py:512`) | YES — type-wall refusal — but **drill-only consumer** | gate_receipt, `origin_mode`-stamped | AG (core) | zoning §Evidence-classes/§3 | **active-and-owned** (drill-only) |
| **StandingSpendabilityGate** (`standing_spendability.py:250`) | YES — chain short-circuit — **drill-only consumer** | gate_receipt, content-addressed | AG (core) | campaign-standing-before-spendability; clock-witness-spec | **active-and-owned** (drill-only) |
| LA clients (`standing_client.py`, `linear_accountant_client.py`) | Live in chain, **SPEC stub — never mints** | emits gate_receipts | `~/git/standing`, `~/git/linearaccountant` | campaign-standing-before-spendability (S1-S3 CLOSED) | **transitional** (correct delegation adapter) |
| profiles.py / autopilot.py | partly — via `.envelope`→`wrapper.py` receipt-relaxation | unreceipted file writes | AG (core) | **none** | **transitional / unruled custody** |
| overrides.py (`OverrideManager`) | partly — feeds *advisory* constraint projection | **log file, NOT content-addressed** (despite "Receipt") | AG (core) | `GOV_GAP_OVERRIDE_ACCUMULATION_001` (counting only) | **transitional / unruled custody** |
| chain_gate / constraint_gate (daemon-wired) | verdict emitted, **default DETECT_ONLY / fail-open** | gate_receipts | AG (core) | `GOV-GAP-CHAIN-001`; in-code contract | **transitional** (advisory by default) |
| evidence_gate / admissibility | BLOCKED/HARD verdict but **consumer is CLI/oracle**, not write-gate | gate_receipt / persisted | AG (core) | feature-history; ADMISSIBILITY_SPEC | **transitional** |
| Claude Code **standalone** pre-tool hook (`claude_hooks.py:164`) | YES — `exit(2)` blocks; **fail-OPEN on bad stdin** (`:146`) | self-log | AG (core) | **none for the fail-open** | **transitional / unruled hole** |
| Gemini adapter block (`gemini_cli.py:88`) | YES — `exit(2)`; **fail-OPEN** on socket error | supervisor-side events | AG (core) | **GAP-M** (ruled-as-deferred, tock-01) | **transitional** (known-open) |
| Scope Governor (`scope.py`) | NO inline runtime gate (CLI + snapshot only) | escalation receipt (gate_receipt-convention) | AG (substrate) | zoning §3; spendability-gap (`use_count`=testimony, KILLED) | **parked** |
| Standing chain validator (`standing/`) | NO consumer (tests only, by design) | sealed ValidationReceipt | AG (constitutional substrate) | validator_contract + v0_1..4 decisions; `..._SEALED_OUTCOME_BOUNDARY_001` | **parked** |
| RunBudgetLedger / BudgetPolicy | YES (1 of 4 dims) — supervised tool-call deny | EventBus events, no hash-bind | **Linear Accountant** | `post-mvp-debt-ba3...`; audit 2026-06-16 | **externally-destined** (BA3) |
| routing `BudgetManager`/`Budget` | NO live consumer | none | **Linear Accountant** | `post-mvp-debt-ba3...` | **externally-destined** (BA3) |
| ExecutionBudget (`execution.py`) | gates only the **noop** autonomous loop | JSON checkpoint, no receipt | **Linear Accountant** (or BA1) | `post-mvp-debt-ba3...`; spendability-gap LOW | **externally-destined** (BA3) |
| ExplorationBudget (`homeostat.py`) | intra-controller energy (tuning state) | advisory | **LA or BA1-by-scope** | `post-mvp-debt-ba3...` | **externally-destined / likely-reclassify-down** |
| ModelRegistry / Router / Lane / CascadeExecutor (`routing.py`/`lanes.py`) | dormant — model-selection path behind `use_lanes` flag w/ **zero callers** | optional `lane_routing` receipt (dormant path) | AG (core) | `GOV_GAP_BUDGETED_EXECUTION_001` | **parked / transitional** |
| RoleBudget (`quorum.py`) | NO enforcer (read-only accessor) | none | n/a | none (harmless) | **dead** |
| `strict.py` `StrictModeGate` | CLI-only; `.strict_mode` file has **no runtime reader** | gate state JSON | AG (core) | none | **dead/parked** |
| **mcp_safety.py** (RateLimiter, BackpressureController, CircuitBreaker, LatencyEnforcer, ShedPolicy) | **NO consumer anywhere** — entirely unimported | none | **unassigned** | **none — shipped feature, no ruling** | **dead + UNRULED** |

### Genuinely unruled seams (candidates only — non-binding, NOT campaigns)

After the doctrine-first search came up empty:

1. **`GOV_GAP_MCP_SAFETY_DISPOSITION_001`** (candidate name reserved) — `mcp_safety.py`
   is a shipped "MCP Safety Controls" subsystem (`feature-history.md`) that **no
   production path imports**. No gap/debt/decision dispositions it. It is either
   (a) dead weight to formally retire, or (b) self-protective infrastructure that
   *should* be wired (rate-limit / backpressure / circuit-breaking on the daemon /
   MCP server) and isn't. Disposition decision needed; this is the one place the
   census found a shipped-but-undispositioned authority surface. **NOT a wire-it-now
   authorization** (that would repeat the P4 dependency-reversal error — find the
   forcing case first).
2. **Override custody** — `OverrideReceipt` is a plain JSON log, not content-addressed,
   despite being a scoped exception to *invariant anchors* (the highest-authority op
   in its cluster). `GOV_GAP_OVERRIDE_ACCUMULATION_001` governs only *counting*
   overrides, not custody. Custody-honesty gap on a real authority-bypass artifact.
3. **Profile/autopilot posture-switching** — `profiles.py` and `autopilot.py` both
   write `.envelope`/`.strict_mode` (which relaxes the receipt gate in `wrapper.py`)
   via unreceipted file writes, with no doc reconciling the duplication or governing
   the custody of switching governance posture.
4. **Standalone Claude-hook fail-open** (`claude_hooks.py:146-148`) — the *unsupervised*
   CLI pre-tool hook fails OPEN on invalid/empty stdin with no governing doc. Distinct
   from GAP-M (Gemini, which IS ruled-as-deferred). The supervised path is the hardened
   successor; if the standalone hook is still an advertised integration, this hole is
   unruled.

### Verdict

**On the capacity / spendability axis: AG is at a legitimate stopping point.** Every
live capacity-authority surface (RunBudgetLedger, routing Budget, ExecutionBudget,
ExplorationBudget) is already ruled BA3 and **parked behind the LA-wiring trigger**.
The LA clients are the correct delegation adapters, sitting as SPEC stubs that never
mint. There is **no unruled capacity authority** and nothing to build here until LA
lands. The operator's hypothesis — "outrun its substrate, not out of ideas" — holds on
this axis.

**On the admission/denial axis:** the production-enforcing gates (git pre-commit,
supervisor pre-tool, egress) are active-and-owned and well-custodied. The richest
authority logic (origin fence, standing-spendability, standing validator) is
ratified-and-correct but **consumer-starved** — invoked only by the drill harness or
not at all. That is by design (waiting on a production spend path), not a gap.

**Net:** the census found **zero unruled capacity authority** and **four non-capacity
unruled seams**, all of which are *completeness / disposition / custody-honesty* items,
not new architecture. The largest single finding is `mcp_safety.py` being
shipped-dead-and-undispositioned. None of the four justifies a build campaign now; #1
needs a disposition ruling, #2-#4 are honesty/coverage debt that can ride existing
debt records. The stopping-point read is substantially correct: AG's remaining live
authority is owned, parked, or delegated, and net-new authority work is gated on
substrate (LA) that hasn't landed.

