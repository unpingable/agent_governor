# Campaign card — AG bootstrap-lab walking skeleton (cold admission)

**Opened:** 2026-06-16
**Status:** COLD-ADMITTED, build NOT started (one fork awaits operator fiat — see §Open).
**Provenance:** operator reframe after the mcp_safety retirement. The "AG is at a
legitimate stopping point, wait for LA" read was an over-correction —
*"guarding against Potemkin machinery and accidentally proposing no machinery."*

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
