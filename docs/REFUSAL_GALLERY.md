# Refusal Gallery

> **STATUS: CANDIDATE (public-mvp S3) — not minted.**
> Every specimen below was live-verified on 2026-07-05 (commands run, exit
> codes observed directly — never through a pipe). Refusal here is a product
> surface, not an error state: each organ refuses with a **typed reason on a
> receipt**, so you can check *why* without trusting prose.

Eight specimens, eight organs, all runnable by a stranger with no network, no
LLM, and no live infrastructure. Longest prerequisite is one `cargo build
--release` (~1 min).

A note on exit codes: some organs exit nonzero on refusal (the refusal blocks
a caller), others exit 0 (emitting a refusal *verdict* is that tool's success
path — e.g. a review packet that says "blocked" was produced correctly). Each
entry says which, and why.

---

## 1. Agent Governor — the stale yes

Same credential, same standing, same admission gate. The only difference is
*when* the spend happens: one second past the horizon.

```bash
cd agent_governor && pip install -e .
./demo/refused-spend.sh
```

```
IMPOSTOR  —  exercise at t=51, one second past the horizon
  standing       verified      ← the credential WAS valid
  wicket         admitted      ← naive auth says yes here
  spendability   REFUSED       standing_before_spendability_not_bounded
    gap=11s  vs bound=10s  → over by 1s
  → refused. No capacity spent (effect_count=0).
```

**Typed reason:** `standing_before_spendability_not_bounded` · **Exit 0**
(the demo's integrity tripwire *fails loudly* if the impostor is refused for
the wrong reason). Full walkthrough: [TOUR.md](TOUR.md).

## 2. NQ — verified AND refused in the same receipt

NQ verifies what its witness can see and refuses the consequence claims it
cannot own — in one receipt.

```bash
cd nq && cargo build --release
./target/release/nq-monitor witness git-status --subject repo:. > /tmp/w.json
./target/release/nq-monitor verify --claim safe_to_merge --subject repo:. \
  --witness /tmp/w.json --strict
```

```
Claim:    safe_to_merge
Status:   not_verified
Reasons:  non_mintable, suggested_weaker_claim_available
Verified:
  - repo_clean
Suggested weaker claims:
  - ready_for_review
```

**Typed reason:** `non_mintable` — `safe_to_merge` needs consequence
ownership the witness layer deliberately does not have. `repo_clean` IS
verified; the refusal is scoped, not global. · **Exit 1** with `--strict`
(informational exit 0 without).

## 3. Nightshift — no packet from a silent witness

A review packet is only as good as the witness it reconciled against. When
the NQ liveness witness has gone silent, Nightshift halts *before consulting
any findings* — and the packet says so.

```bash
cd nightshift && cargo build --release
# stale-liveness fixture + nq stub: inlined in README's 30-second specimen
./target/release/nightshift --nq-liveness /tmp/ns-specimen/stale-liveness.json \
  --nq-bin /tmp/ns-specimen/nq-stub ... watchbill run ...
```

```yaml
reconciliation_summary:
  blocked:
  - 'liveness_gate: liveness stale: witness silent for 600s (threshold 90s)'
  ok_to_proceed: false
diagnosis:
  regime: 'stale: NQ liveness gate did not clear; no findings consulted'
```

**Typed reason:** `liveness_gate` block, `ok_to_proceed: false` · **Exit 0**
(emitting the blocked packet is the correct output — a slightly-worse packet
would be the failure). Fixture-backed; no live NQ needed.

## 4. Wicket — recommend-standing can't reach execute

Basis satisfied, precedence satisfied — and still denied, because standing is
checked as its own dimension. Recommend-class standing does not launder into
execute-class operations.

```bash
cd wicket && cargo build --release
./target/release/wicket commit --because "publish the release" \
  --irreversible --standing execute --brief
```

```
DENIED  commit wicket@HEAD
  reasons: BASIS_INADMISSIBLE_BIND_REQUIRES_HUMAN_CONFIRMATION, PRECEDENCE_OK, STANDING_OK
  allowed: supply_admissible_basis
  forbidden: mutate_target, claim_authorization
  receipt: sha256:d5061145…
```

**Typed reasons:** dimensional — the fixture corpus
(`cases/laundering/`) includes `STANDING_INSUFFICIENT_FOR_OPERATION` with
basis and precedence both green. · **Exit 0** (denied is a successful
verification; `--strict-exit` for nonzero).

## 5. Standing — the grant expired while you held it

Nothing about the credential, policy, or identity changed. Only time passed.

```bash
cd standing && cargo build --release
standing grant request … --duration 1   # granted, expires in 1s
standing grant activate …
sleep 3
standing grant use …
```

```
error: grant expired at 2026-07-05T18:27:01.202282825+00:00
```

**Typed reason:** `grant expired` + precise timestamp · **Exit 1.** The
receipt chain (issued → activated → refused) survives in the store:
`standing query why --id <grant-id>` walks it after the fact.

## 6. Continuity — observed is not committed

An agent wrote a memory. That makes it *findable*, not *reliable*.

```bash
cd continuity && pip install -e .
contctl --db demo.db init
contctl --db demo.db observe --scope demo --kind fact --basis direct_capture \
  --content '{"topic":"auth-migration","status":"blocked on legal review"}'
contctl --db demo.db why mem_c5cddf…
```

```
REFUSED  [status_not_committed]  mem_c5cddf4141fd45a5a64dfbe2ef581cae
  memory status is observed, not committed
    authoring_tier: agent_authored
    effective_reliance: none
```

**Typed reason:** `status_not_committed` · **Exit 1.** After an explicit
`commit --reliance-class advisory`, the same query answers `RELY OK`.

## 7. Porter — no exit code, no delivery

The courier refuses when it cannot observe the one fact it exists to carry:
the true exit code.

```bash
cd porter
./demo/refused-exit.sh
```

```
"outcome": "refused",
"refusal_reason": "command exit code was not observed; ssh exited 255",
"exit_code_observed": false        ← and no exit_code field at all
Porter process exit: 1
```

**Typed reason:** `outcome: refused` with `exit_code_observed: false` —
porter never guesses, and its outcome vocabulary contains no domain words
(`success`/`passed`/`admissible` are structurally banned, pinned by test).
· **Exit 1.**

## 8. Verifier — the fact aged out of the proof

The grant existed and matched scope. It was expired at decision time, so the
solver never saw it — and the verdict names exactly what was dropped.

```bash
cd verifier && pip install -e .
verifier-check examples/stale-standing-denied.json
```

```json
{
  "status": "denied",
  "failed_rules": [{ "rule_id": "standing.scope_match", "kind": "standing" }],
  "used_facts": [],
  "stale_facts": [{ "source": "standing:grant-101", "claim_state": "expired" }]
}
```

**Typed reason:** `status: denied`, `claim_state: expired` in `stale_facts`
· **Exit 0** (a verdict, not a crash). Golden output pinned at
`examples/stale-standing-denied.verdict.json`.

---

## What the gallery is telling you

The same shape recurs in every organ: **a typed reason, on a receipt, at a
named seam** — never a log line you have to trust. And the seams differ on
purpose: time (AG, Standing, Verifier), witness liveness (Nightshift),
consequence ownership (NQ), authority class (Wicket), reliance status
(Continuity), observability (Porter). No organ requires another; each refusal
runs standalone.

What this gallery does NOT claim: that these fences bind an actor with
filesystem access to the stores (documented bootstrap limit), that live agent
execution is enabled anywhere (it is refused by construction), or that a
schema-valid artifact is ever admission.
