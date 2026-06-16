# Campaign card — AG bootstrap-lab walking skeleton (cold admission)

> **AMENDED 2026-06-16 (operator) — the tunable fork (§Open A/B/C) is REJECTED.**
> The `ActiveTunableStore` requirement was misframed: `max_actions` **is capacity
> authority**, and LA already owns and implements that concept (complete, frozen,
> tested — `/home/jbeck/git/linearaccountant`). So: do NOT widen the P3.1 store,
> do NOT reuse `max_slices`, do NOT create a parallel lab custody store, do NOT
> make the lab runtime a pretext to alter P4's activation boundary. The action
> bound comes from an **LA capacity grant**, not an AG self-annealing tunable.
>
> **New topology:** operator → controller/outer Claude → AG supervised session →
> LA capacity decision → worker/inner Claude tool effect. AG mediates a real
> planner/worker split; the outer Claude reacts to refusals and receipts. More
> bugs, found sooner.
>
> **New first slice (narrower than "build the whole skeleton" — most of the
> supervised machinery already exists):**
> > Wire ONE AG supervised tool-effect boundary to ONE LA capacity `consume`
> > decision, under `profile=bootstrap_lab`, with no P4 or production-promotion
> > claims.
>
> **Acceptance (amended):**
> 1. outer Claude can create and drive an AG-supervised inner session;
> 2. one inner tool class crosses only after LA authorizes consumption;
> 3. an exhausted / replayed grant refuses the effect;
> 4. AG records the LA request/decision identity in its event/receipt trail;
> 5. two concurrent attempts against one unit → exactly one effect;
> 6. NO `ActiveTunableStore` changes;
> 7. no BA3 authority survives as a competing decision-maker;
> 8. no promotion evidence minted.
>
> Components 1/2/4/5/6 of the original (entry point, sandbox actuator, governance
> path, replay, scope label) still hold; original component 3 (intrinsic tunable
> from `ActiveTunableStore`) is **replaced** by the LA-backed effect gate. §Open
> below is superseded by this amendment.
>
> **One cross-repo sub-decision remains (the real bridge):** a genuine LA decision
> from AG-Python needs a transport — LA is a Rust library with "no binary" by
> design. Options: (i) subprocess to a thin LA CLI bin, (ii) PyO3 in-proc link,
> (iii) build the AG-side gate first against the EXISTING injected-callable seam
> in `linear_accountant_client.py` (contract-faithful, what LA's own tests use),
> then swap the real bridge in. LA's "no new slices without a consumer trigger"
> rule is now satisfied — the trigger has fired — so a minimal LA bin is licensed,
> but it touches the LA repo (dedicated owner) and should be flagged, not done
> unilaterally. Recommended sequence: (iii) then (i).

**Opened:** 2026-06-16
**Status:** COLD-ADMITTED + AMENDED to the LA-backed effect gate (above). Fork A/B/C rejected. AG-side build (against the injected LA seam) is unblocked; the real LA bridge is a flagged cross-repo follow-on.
**Provenance:** operator reframe after the mcp_safety retirement. The "AG is at a
legitimate stopping point, wait for LA" read was an over-correction —
*"guarding against Potemkin machinery and accidentally proposing no machinery."*

## Build plan — slice 1 (grounded, AG-side, no cross-repo)

Reconned attach points (file:line):
- **LA client seam** — `linear_accountant_client.py:339` `LinearAccountantClient`,
  ctor takes injected `request_capacity_callable` / `consume_callable` /
  `admission_verifier` / `receipt_sink`; `.consume(CookedConsumeRequest, now,
  parent_grant_receipt_id=) -> ConsumedResult | RefusalResult` (:716). Replay →
  `already_consumed`; exhaustion → `capacity_refused`; emits GateReceipts. This
  injected seam is contract-faithful (what LA's own tests + the orchestrator use)
  → slice 1 needs NO real LA bridge.
- **Tool-effect boundary** — `runtime/supervisor.py:534` `_handle_tool_proposed`
  (the existing pre-tool gate; today a BA3 budget deny sits here). Under
  `bootstrap_lab`, the LA `consume` decision becomes the gate for the chosen tool
  class and the BA3 budget gate must NOT also act (acceptance §7).

Design defaults for slice 1 (override if wrong):
- **Grant lifecycle:** one LA `request_capacity` per supervised session at launch
  (N units = the action bound); each governed tool effect of the chosen class does
  one `consume(amount=1)` against the session token. The action limit is thus the
  LA grant, not an AG tunable.
- **Chosen tool class:** the reversible sandbox actuator (temp-file write /
  subprocess `echo`) — observable effect on `Consumed`, observable refusal on
  `capacity_refused`/`already_consumed`.
- **Testable core first:** the `bootstrap_lab` LA-backed effect gate as a unit
  (injected `consume_callable` mirroring `InMemoryAccountant` — grant/consume/
  replay-kill/exhaustion), provable for acceptance §2–§5 + §7–§8 + concurrency
  WITHOUT spinning a real Claude backend. The supervisor "outer drives inner"
  integration (§1) layers on top once the gate core is green.
- **Fence (§6 of original / §7-§8 amended):** `profile=bootstrap_lab` tag on the
  session + receipts; a load-bearing test that lab receipts cannot be consumed as
  promotion/production evidence and cannot mutate `ControlBaseline`.

## Forcing case (independent — NOT P4)

A **runnable AG** is itself an independently-justified forcing case: integration
velocity, observability, and dogfooding all require an actual end-to-end loop,
not a collection of correctly-fenced organs in jars. This is the legitimate
version of "build ahead of production":

- **Bad:** invent a fake production control so P4 can promote something.
- **Good (this):** build an explicitly **bootstrap/lab runtime** whose purpose is
  to make AG execute end-to-end. It may consume governed tunables and emit real
  receipts; its evidence **cannot** claim production safety or authorize
  production baselines.

## Question

> Can AG run the smallest genuine governed action loop — one real entry point,
> one bounded sandbox actuator, one intrinsically-needed control resolved once
> per run from a custodied store — with admission/receipts/replay, fail-closed
> on absent/malformed governed state, and a hard scope label that bars
> production and P4 claims?

## The six components (acceptance criteria)

1. **One real entry point** — a CLI (or daemon) command that is a runtime, not a
   drill helper wearing a runtime hat. (Attach: new `governor lab run` in
   `cli.py`; NOT the existing `autonomous run`, whose loop is a noop —
   `executor.py`/`cli.py:11014`.)
2. **One bounded action surface** — reversible sandbox actuator: temp-dir/file
   ops or subprocess `echo`. Actions must have **observable effects AND
   observable refusals**.
3. **One intrinsic control** — something the loop actually needs (`max_actions` /
   `max_steps`). Resolved **once per run** from `ActiveTunableStore`
   (`activation.py:294`, `.get(surface,target)`). **`4` vs `8` must change the
   execution trace, not just metadata.** (See §Open — the store is P3.1-locked.)
4. **Existing governance path** — admission before action (`admissibility.py`);
   intra-lab budget/accounting where valid (BA1-by-scope, NOT authoritative
   spendability — must not pose as LA); receipts (`gate_receipt.py` GateReceipt +
   ReceiptStore) **bound to run · activation · decision · effect**; **fail closed**
   when governed state is absent or malformed.
5. **Replay** — reconstruct what was admitted, refused, and executed from durable
   artifacts (receipts/event log). **No claim that replay proves general safety.**
6. **Hard scope label** — `profile = bootstrap_lab`:
   - cannot mint production promotion evidence;
   - cannot mutate `ControlBaseline`;
   - **cannot satisfy the parked P4 trial by itself.**

## Invariant (load-bearing fence)

The bootstrap_lab scope label is the firewall. This campaign produces a real
governed loop and a genuinely-consumed tunable **for dogfooding**, and is
forbidden — by label, enforced — from being cited as P4 production-actuator
evidence or from touching production baselines. P4 stays PARKED
(`working/P4_PARKED_2026-06-16.md`); this does not reopen it.

## Allowed

- New `bootstrap_lab` runtime module + CLI entry + sandbox actuator + replay.
- Consume a governed tunable; emit real (lab-scoped) receipts.
- Reuse existing admission / receipt / activation machinery as the integration bench.

## Forbidden

- Any path by which lab evidence mints production promotion evidence or mutates
  `ControlBaseline`.
- Claiming this satisfies P4's trial (the consumer exists for dogfooding, not to
  rescue P4 — the distinction is scope-enforced, not honor-system).
- A sandbox actuator that is not reversible / not observable.
- Silent fail-open on absent/malformed governed state.

## Open (operator fiat required before code) — the tunable fork

`ActiveTunableStore` currently admits **only** the P3.1 tunable
(`decomposition_size/max_slices`); `apply_activation`/`apply_rollback` refuse any
other `(surface,target)` (activation.py:344, 371). "Resolve from
`ActiveTunableStore`" therefore forces one of:

- **Fork A — reuse the P3.1 tunable.** Skeleton reads `get(P31_SURFACE,
  P31_TARGET)` and uses `max_slices` as `max_actions`. *No fence change; minimal
  blast radius.* But it reuses **P4's exact tunable** — even under bootstrap_lab
  scope, that is laundering-adjacent to the consumer P4 was forbidden.
- **Fork B — widen the store for a lab tunable** (`bootstrap_lab/max_actions`),
  relaxing the P31 "exactly one tunable" lock to admit a second declared target.
  *Clean semantics; strongest P4 firewall* (skeleton consumes a DIFFERENT
  tunable, never P4's). But it changes the ratified P3.1 fence — custody-adjacent,
  needs a ruling.
- **Fork C — lab-local store** (not `ActiveTunableStore`). Cleanest isolation but
  contradicts the explicit "from `ActiveTunableStore`" instruction.

**Recommendation: B** — it honors "from ActiveTunableStore" while keeping P4's
decomposition tunable pristine, which is the firewall the campaign needs. It
costs a deliberate, ruled widening of the P3.1 "exactly one tunable" property
(add a second sanctioned `(surface,target)`, not an open registry).

## Exit states

- (a) Skeleton runs: one entry point, one consumed tunable where `4≠8` in the
  trace, admission+receipts+replay, fail-closed, bootstrap_lab fence holds → the
  integration bench exists; wire standing / origin-fence / override-custody /
  activation / observation / (eventually) LA onto it next.
- (b) A component proves infeasible under the fence → record which and why.

## Downstream (why this unblocks everything)

Once the bench exists it is where standing, origin fencing, override custody,
activation, observation, and eventually the LA `CapacityRequest`→`consume` path
get wired and *exercised* — turning correctly-fenced organs into a circulatory
system. LA itself is complete/frozen/ready (orientation 2026-06-16); the wiring
gap was always AG-side, and the bench is where AG closes it.
