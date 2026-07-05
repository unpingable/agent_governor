<!-- STATUS: CANDIDATE (public-mvp S2) — not minted -->

# Guided Tour: A Stale Yes, Refused

A narrated walkthrough of the three-script demo path. Each command is literal;
each receipt field is explained. No LLM, no network, no clock required.

---

## What you need

```bash
git clone https://github.com/unpingable/agent_governor
cd agent_governor
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

> If `pip install -e .` gives `ModuleNotFoundError: No module named 'yaml'`,
> your checkout predates 2026-07-05 (`pyyaml` moved into the base
> dependencies after fresh-clone verification caught this); `pip install
> pyyaml` unblocks older checkouts.

---

## Act 1 — A stale yes (`demo/refused-spend.sh`)

```bash
./demo/refused-spend.sh
```

**What it does.** Runs two actions through the identical gauntlet. Both have the
same standing observation (verified at monotonic time `t=40`, horizon at `t=50`).
They differ only in *when* the spend is attempted:

- **Legitimate twin** — spends at `t=45`, inside the horizon. Admitted.
- **Impostor** — spends at `t=51`, one second past the horizon. Refused.

The credential was valid when checked. Ordinary auth — "is the credential still
valid?" — would let both through. The custody layer sees the gap between
*observation time* and *exercise time* and refuses the late spend.

**The output you see:**

```
IMPOSTOR  —  exercise at t=51, one second past the horizon
  standing       verified      ← the credential WAS valid
  wicket         admitted      ← naive auth says yes here
  spendability   REFUSED       standing_before_spendability_not_bounded
    gap=11s  vs bound=10s  → over by 1s
    gap_basis: monotonic, source=process_monotonic epoch=boot:demo-single-host
    wall 2026-06-09T00:00:40Z [display_only] — display only, NOT the gap basis
```

**The two clocks.** The gap is computed on a *monotonic* reading — a pair of
nanosecond timestamps from one source and one epoch (here: `process_monotonic` /
`boot:demo-single-host`). Monotonic clocks never step backward; wall clocks do
(NTP adjustments). A gap computed across a wall-clock step would be garbage
wearing an ISO 8601 smile. The code (`src/governor/clock_witness.py`) refuses
to subtract incompatible readings. The wall timestamp in the output is labeled
`display_only` — it is shown for human readability but is not the gap basis and
carries no admission weight.

**Where the receipts land.** The script prints the path:

```
Receipts written under: /tmp/ag-refused-spend.XXXXXX
```

Inside that directory:

```
/tmp/ag-refused-spend.XXXXXX/
  impostor/.governor/
    receipts/gate_receipts.jsonl      ← three chained receipts (JSONL, one per line)
    evidence/<hash-prefix>/<hash>.json ← evidence bundles (content-addressed by sha256)
  twin/.governor/
    receipts/gate_receipts.jsonl      ← five receipts (pass through all gates)
    evidence/...
```

**The impostor's three receipts** (from `gate_receipts.jsonl`, one JSON object per line):

1. `gate: standing_seam, verdict: pass` — standing was verified (credential OK).
2. `gate: wicket_seam, verdict: pass` — wicket's admissibility preflight passed.
3. `gate: standing_spendability_seam, verdict: block` — custody diverges here.
   The refusal receipt names the predicate:
   `refusal_kind: standing_before_spendability_not_bounded`.

**The evidence bundle for receipt 3** (at `.governor/evidence/b4/b4b6...json`):

```json
{
  "gap_ns":     11000000000,
  "bound_ns":   10000000000,
  "overage_ns":  1000000000,
  "bounded":    false,
  "gap_basis": {
    "kind":    "monotonic",
    "source":  "process_monotonic",
    "epoch":   "boot:demo-single-host",
    "start_ns": 40000000000,
    "end_ns":   51000000000
  },
  "wall": { "role": "display_only", ... },
  "refusal_kind": "standing_before_spendability_not_bounded",
  "origin_mode": "drill"
}
```

`gap_ns > bound_ns` is the falsifiable predicate. `gap_ns = end_ns - start_ns`
on matching `(source, epoch)`. A mismatch raises `GapBasisMismatch` — the code
never subtracts incompatible clocks.

`origin_mode: drill` — simulated scenario. Receipts are evidence, not authority.
Schema-validity is never admission.

**The integrity tripwire.** The script exits non-zero if the impostor was
*not* refused for the right reason — for instance, if a short-circuit prevented
the temporal check from running at all. A demo that passes for the wrong reason
fails loudly.

---

## Act 2 — Cross-examine the corpse (`demo/interrogate.sh`)

```bash
./demo/interrogate.sh          # no argument: runs Act 1 fresh, then Act 2 + 2.5
./demo/interrogate.sh /tmp/ag-refused-spend.XXXXXX   # or pass Act 1's root
```

Six questions, each a runnable `governor` command. The custody chain
reconstructs from receipts on disk — not from logs, not from memory.

**Q1 — What happened to the spend?**
`governor --root <impostor-dir> why <receipt-id>` — walks the chain: refusal →
wicket → standing → honest `MISSING` terminus (the NQ origin finding is not
local; its absence is named, not papered over).

**Q2 — Why was it refused?**
`governor --root <impostor-dir> receipts --id <receipt-id> --evidence` — the
typed refusal kind (`standing_before_spendability_not_bounded`) is on the
receipt itself, not inferred from a log message.

**Q3 — Which predicate failed?**
`gap_ns = 11 000 000 000`, `bound_ns = 10 000 000 000`, `overage_ns = 1 000 000 000`
(nanoseconds). The gap exceeded the bound by exactly one second.

**Q4 — Under which clock witness?**
`gap_basis.source = process_monotonic`, `epoch = boot:demo-single-host`. The
wall clock is `role: display_only` — not the gap basis.

**Q5 — What did the naive gate conclude?**
The OPA verdict is already in the evidence plane at `<root>/opa_verdict_receipt.json`.
If OPA is absent: `engine: opa_not_installed`, no verdict fabricated.

**Q6 — A receipt that doesn't exist?**
`governor --root <impostor-dir> why 0000...0000` → `receipt id not found`.
Honest absence. Never inferred.

The interrogation exits non-zero if any assertion fails.

---

## Act 2.5 — What a policy engine would have said (`demo/opa-contrast.sh`)

```bash
./demo/opa-contrast.sh
```

**What it does.** Runs the same impostor incident through a small Rego policy
(Open Policy Agent). The policy is correct for the world it is handed:

```rego
package demo.authz
default allow := false
allow if {
    input.credential.status == "valid"
    input.credential.role   == "operator"
    input.action            == "consume_capacity"
}
```

The input document asserts `credential.status = "valid"`. It does not attest
*when* that was true. OPA, if installed, returns `allow`. Custody refuses
upstream, before the policy sees the claim, because the standing lapsed in
the gap.

**The point.** Policy engines decide over claims. Custody systems decide whether
those claims may *become* premises. OPA is not wrong — it is answering the
question it was given. The question it was given was not falsified.

**If OPA is not installed.** The script says so plainly and shows the 8-line
policy and input by eye. No verdict is fabricated. The output names
`engine: opa_not_installed`.

**The OPA verdict receipt** lands at `<root>/opa_verdict_receipt.json`:

```json
{
  "receipt_id": "opa_rcpt_d705b58dc2d4",
  "kind": "opa_verdict",
  "policy_hash": "sha256:7626...",
  "input_hash": "sha256:7013...",
  "input_provenance": "unwitnessed_self_report",
  "decision": null,
  "engine": "opa_not_installed"
}
```

`input_provenance: unwitnessed_self_report` means the input document was
assembled by the demo itself — it is not an externally witnessed fact. This
label is structural discipline, not a verdict. The custody receipts live in
`<root>/custody/.governor/`.

---

## Vocabulary used in this tour

**Standing.** A verifiable claim that an actor is authorized to take some action,
issued at a specific time. Standing is observed; it is not continuously valid.

**Spendability.** The judgment that a standing observation, at exercise time, is
still within its horizon. Standing valid when observed does not license a spend
after the window expires.

**Horizon / bound.** The max gap (nanoseconds) between when standing was observed
(`start_ns`) and when the spend is attempted (`end_ns`). `gap_ns > bound_ns` →
refused.

**Monotonic clock witness.** A nanosecond reading from a named `(source, epoch)`.
Gaps are computed only between compatible witnesses. Wall timestamps are labeled
`display_only` — not the gap basis.

**Receipt.** A content-addressed, hash-chained record of a gate decision. The
evidence bundle is stored separately, addressed by `sha256:<hex>`. Receipts are
evidence; schema-validity is never admission.

**Evidence bundle.** Structured data a gate checked. Stored under
`.governor/evidence/<prefix>/<hash>.json`. Content-addressed — the hash in the
receipt is the integrity link.

**Refusal kind.** A typed, closed-vocabulary reason code on the receipt. Never a
free-text log message.

**origin_mode.** Provenance label: `drill` = simulated scenario, evidence fenced;
`observed` = live operational event (only mode that may confer operational effect).

**Wicket.** Single-call admissibility preflight gate. In the demo it passes for
both twin and impostor — the temporal-lapse check is downstream, at the
spendability seam.

**Honest absence.** Receipt not found → `receipt id not found`. Never inferred.

---

## Where to go next

| Goal | Doc |
|------|-----|
| Add a rule and see a gate block | [docs/GETTING_STARTED.md](GETTING_STARTED.md) |
| Run a supervised agent session | [docs/SUPERVISED_MODE.md](SUPERVISED_MODE.md) |
| Understand receipts and admissibility | [docs/ADMISSIBILITY.md](ADMISSIBILITY.md) |
| See all CLI commands | `.claude/rules/cli-reference.md` |
| Architecture and design lineage | [docs/BACKGROUND.md](BACKGROUND.md) |
