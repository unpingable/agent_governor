# P4 — activation-tunable consumer-reachability audit (read-only, 2026-06-16)

Operator-admitted read-only audit, run after `max_slices` was falsified, to test
whether **any** activation-allowlisted tunable has an operational referent — so
"P4 trial evidence is architecturally premature" is *established*, not inferred one
step early. **No code. No retargeting.** Disposition is the operator's call.

Proposition under test (operator): *the framework may currently govern declarations
of control rather than operational control.*

## Method

- **Step A (decisive, COMPLETE — not sampled):** the activation transaction
  (`activation.py`) writes its value to exactly one place — `ActiveTunableStore`
  (`.governor/active_tunables/values.json`, key `surface/target`). Grep across
  `src/` + `libs/`: `ActiveTunableStore` / `active_tunables` appear **only inside
  `activation.py`** (class def + path + the two writer fns). **Zero readers, zero
  importers.** So no allowlisted tunable's *activated value* is consumed — uniformly,
  by construction, regardless of naming.
- **Step B (per-surface, synonym-aware):** five read-only sub-audits (one per
  remaining surface) traced whether each target *concept* has a live production
  consumer reading its OWN config — a potential retarget candidate — excluding tests,
  drills (`drill_runner.py`), demos (`webui_demo.py`/`demo_*`), and dead/SPEC-harness
  surfaces. The distinction enforced throughout: *reader of the value/store*, never a
  *similarly-named constant*.

## Findings — all 6 surfaces, 17 targets

| Surface | Target | Live consumer of the *concept* | Reads from | Consumes *activated value*? | Verdict |
|---|---|---|---|---|---|
| decomposition_size | max_slices | none (no slice executor) | — | no | NO_CONSUMER |
| decomposition_size | slice_cap | none | — | no | NO_CONSUMER |
| routing | lane_weights | none (computed from LANE_CONTRACTS) | — | no | NO_CONSUMER |
| routing | escalation_threshold | none (hardcoded thresholds) | — | no | NO_CONSUMER |
| routing | fallback_order | none (built from ModelRegistry) | — | no | NO_CONSUMER |
| budgets | retry_budget | none | ProfileConfig (not read back) | no | DISCONNECTED |
| budgets | capacity | none | LA response / BudgetPolicy | no | DISCONNECTED |
| budgets | attention_budget | none | not found | no | DISCONNECTED |
| budgets | time_budget | none | not found | no | DISCONNECTED |
| retry_posture | retry_budget | none | `.autopilot` (written, never read) | no | DISCONNECTED |
| retry_posture | **backoff_base** | **`mcp_safety.py:162`** (RateLimiter) | **hardcoded `RateLimitConfig`** (1.5) | **no** | **PARTIAL/DEAD** |
| retry_posture | max_retries | none (name absent; homonym hardcoded) | — | no | NO_CONSUMER |
| witness_placement | witness_seam | none | — | no | DISCONNECTED |
| witness_placement | early_witness | none | — | no | DISCONNECTED |
| default_gates | recomposition_shadow | none (it's a `run()` ARGUMENT) | function arg | no | NO_CONSUMER |
| default_gates | shadow_emission | none (it's a `run()` ARGUMENT) | function arg | no | NO_CONSUMER |

**Activated-value consumers: 0 / 17.**

### The one near-miss (and why it is not a retarget)
`backoff_base` is the only target with a live, production-reachable consumer of the
*concept*: `mcp_safety.RateLimiter._calculate_backoff` (`mcp_safety.py:162`) reads
`RateLimitConfig.backoff_base` and a change *does* yield a concrete bounded delta
(exponential backoff: at count=3, `2.0**3=8.0s` vs `1.5**3=3.375s`). But it reads a
**hardcoded dataclass default**, never `ActiveTunableStore`. Pointing activation at it
would mean *rewiring mcp_safety to read the activated store* — i.e. rehabilitating a
disconnected consumer to save the campaign, which the decision tree forbids. It is
also **MCP-client rate-limiting authority** (self-protection infra), not
self-governance — an authority mismatch, not a low-authority match.

## Decision-tree mapping (operator's tree)

- *Exactly one honest live consumer [of the activated value]:* **no** (0/17).
- *Several:* no.
- *Only partial/dead consumers:* **yes** — `backoff_base` is a live concept-consumer
  reading a hardcoded value, disconnected from activation. The tree's instruction:
  *same result; don't rehabilitate one merely to save the campaign.*
- *None [consume the activated value]:* **yes, established by Step A** — complete, not
  sampled.

→ **Both terminal branches that apply point to option 3.** The conclusion is
empirically established, not one inference early.

## Diagnosis — confirmed

> The activation framework is an **actuator registry without actuators.** It governs
> **declarations of control** — you can activate a value into `ActiveTunableStore`
> through the full four-office ceremony (admissibility · standing · exactly-once spend
> · durable custody) and mint receipts about it — but that store is wired to **zero
> operational control.** Every live control surface that exists (routing's
> ModelRegistry, `mcp_safety`'s `RateLimitConfig`, autopilot's `ProfileConfig`,
> `BudgetPolicy`, LA capacity) reads its own separate/hardcoded config, never the
> activated value.

The operator's proposition is therefore **affirmed**: the framework currently governs
declarations of control, not operational control. `max_slices` was not a bad tunable
choice — it was a representative one. The gap is structural to the framework, not
local to the tunable.

## What this does NOT claim
- NOT that AG has no operational control — routing, rate-limiting, budgets are all
  live; they just read their own config.
- NOT that the activation framework is wrong — its admissibility/standing/spend/custody
  machinery is real and tested. What is missing is the *last wire*: a consumer that
  reads the activated value.
- NOT a recommendation to build that wire now (that is option 2, explicitly deferred —
  and for `backoff_base` specifically, forbidden as rehabilitation).

## Stop line
No code, no retarget (audit step 7). The honest disposition — option 3, park the
self-governance trial-evidence path as architecturally premature, OR a deliberate
decision to wire a first consumer under its own admission — is an
operator-present, cold-from-receipts call (per [[feedback_inherit_receipts_not_warm_intentions]]).
This audit is the receipt; the ruling is the operator's.
