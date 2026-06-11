# Witness: B0 — Rendering Audit for `unsettled` Visibility

**Filed:** 2026-06-09. **Scope:** read-only classification. No code changes. Follows the B0 forcing-case audit specified after the Option A golden fixture landed.

## Verdict

**B. Receipt-linked but not visible.**

Operator-facing Nightshift surfaces (packet, run ledger, `runs show`) carry receipt-ID pointers to the Governor receipt but NO `unsettled` content. The only way to read the typed `freshness` claim's `kind` / `reason` is to copy the receipt_id from the packet, switch to the Governor CLI, and run `governor receipts show <id>` — which dumps the receipt as raw JSON (no human-readable text rendering exists for v4 fields).

Implementation **B (rendering)** has jurisdiction. Whether to surface on the Nightshift side, the Governor side, or both is the B-slice's first decision.

## Surfaces inspected (direct reads this pass)

| # | Surface | What it carries about the receipt | Carries `unsettled`? |
|---|---|---|---|
| 1 | `~/git/scheduler/crates/nightshiftd/src/packet.rs:215-247` — `ReceiptReferences.governor_receipts: Vec<String>` | receipt_id strings only | **no** |
| 2 | `~/git/scheduler/crates/nightshiftd/src/reconcile_horizon.rs:330-395` — `outcome_event_payload` (`RunHorizonOutcome` ledger event) | action / finding_key / basis_id / basis_hash / expires_at + receipt_id | **no** |
| 3 | `~/git/scheduler/crates/nightshiftd/src/reconcile_horizon.rs:55-66` — `HorizonReceipt` struct (NS-side) | finding_key / receipt_id / receipt_hash / action / basis_id / expires_at | **no** (field stays Rust-side wire-only) |
| 4 | `~/git/scheduler/crates/nightshiftd/src/main.rs:607` — `runs show` CLI subcommand | renders posture via `render_show(&posture)`; doesn't open the receipt store at all | **no** |
| 5 | `~/git/agent_gov/src/governor/cli.py:1097-1129` — `governor receipts list` (text) | summary line per receipt: verdict-icon / id[:12] / gate / timestamp | **no** |
| 6 | `~/git/agent_gov/src/governor/cli.py:1241-1255` — `governor receipts show <id>` | **unconditionally** `click.echo(json.dumps(receipt.to_dict(), indent=2))` — no text mode | **yes**, but only as raw JSON dump |

Search confirmation: `grep -rn "unsettled\|non_discharge\|NonDischarge"` across `~/git/scheduler/crates/nightshiftd/src/` returns only the populate/wire/test sites (`reconcile_horizon.rs`, `governor_client.rs`). **Zero rendering surfaces mention these names.** Same grep across `~/git/agent_gov/src/governor/cli.py` returns nothing.

## Operator path to read `kind=freshness` / `reason` today

1. Run a horizon-configured `watchbill run` (with `--horizon-policy` + `--governor-socket`). Get the packet YAML.
2. Find the `receipt_references.governor_receipts: [<receipt_id>]` field in the packet.
3. Switch to the agent_gov CLI: `governor receipts show <receipt_id>`.
4. Read the JSON dump. Locate the `"unsettled": [...]` array. Read `kind`, `reason`.

Cross-tool, multi-step, raw-JSON. The packet alone doesn't tell you what the verdict left unsettled — only that some Governor receipt was minted.

## Why this matters

The doctrine line from the prior consolidation note:

> *A gate receipt must distinguish what it permits from what it leaves unsettled.*

Holds at the schema level (v4) and at the population level (Defer → Freshness). But operationally, the *distinction is invisible* to the operator inspecting normal workflow output. The receipt exists; the confession is in a filing cabinet with a tasteful brass plaque labeled with the receipt_id.

This isn't a fatal flaw — the data is preserved, content-addressed, and recoverable. It's a usability/auditability gap. Whether to close it depends on whether operators are actually expected to read `unsettled` content during routine review, vs. only on retrospective audit.

## Justification check for opening B

The user-supplied criterion from the prior slice's "next candidates" section: opening B requires a forcing case of the form *"operator can't tell what a Defer left unsettled from the packet alone."* This audit confirms that exact gap exists today; the criterion fires.

But: "an operator can't see X from surface Y" is a slope, not a binary. The B slice should answer scope questions before code:

1. **Which surface?** Packet rendering, Governor text-mode receipt rendering, or both? Packet is closer to operator workflow; Governor text-mode is closer to audit.
2. **What format?** Inline summary (e.g., one line per claim) vs. a separate `unsettled:` block in the packet YAML?
3. **What threshold?** Render claims when present and skip when empty? Always render `unsettled: []` to make absence-as-positive-claim visible?
4. **Stability concern.** Packet schema is operator-facing. Adding a new field bumps a packet version implicitly. Worth versioning explicitly if downstream tooling parses packet YAML.

None of these need to be answered this pass. B opens with the audit on file; the scope discussion is the B-slice's own first step.

## What this session did NOT do

- **Did not** change any rendering code.
- **Did not** add any new tests or fixtures.
- **Did not** open the B slice. Audit only.
- **Did not** inspect operator-facing docs beyond the ones already audited (operator/README is a TODO stub per the CLI-reachability witness).
- **Did not** consider C (populate another verdict kind) — out of scope for B0.
- **Did not** widen any enum.
- **Did not** touch standing-validator drift.

## Recommendation

Open the B slice when ready. Likely first scope decision: **packet-side first, Governor-text-mode second.** Packet is on the operator's normal path; Governor text-mode is for inspection. If only one slice gets done, the packet rendering is the higher-leverage move.

## Provenance

Filed 2026-06-09 after Option A landed (golden fixture). Read-only inspection across six surfaces in two repos. No code changed; no tests added. Three witness files updated this run (this one, the integration state note for the prior slice, and the prior fixture-landing note) — all consolidating, none widening.
